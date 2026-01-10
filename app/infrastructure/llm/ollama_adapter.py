import json
import httpx
import asyncio
from typing import Dict, AsyncIterator, Optional, List, Any
from loguru import logger

from app.infrastructure.llm.base import BaseLLMAdapter, LLMRequest, LLMResponse
from app.core.config import get_settings
from app.core.resilience import retry

class OllamaAdapter(BaseLLMAdapter):
    """
    Adapter for Ollama API (http://localhost:11434).
    Asynchronous implementation using httpx.
    """
    
    def __init__(self):
        """Initialize Ollama adapter."""
        self.settings = get_settings()
        self.base_url = self.settings.ollama_base_url
        self.model_name = self.settings.llm_model_path
        self._is_loaded = True 
        # Persistent Client (Fix for Performance/Latency)
        self.client = httpx.AsyncClient(timeout=120.0)

    def _load_model(self) -> None:
        pass 

    async def is_available(self) -> bool:
        """Check availability (Async)."""
        try:
             # Use a shorter timeout for health check
             res = await self.client.get(f"{self.base_url}/api/tags", timeout=2.0)
             return res.status_code == 200
        except:
            return False

    def _build_request_payload(self, request: LLMRequest, stream: bool = False) -> Dict[str, Any]:
        """Construct the Ollama API payload."""
        system_prompt = request.system_prompt or (
            "You are a helpful AI assistant. Answer based on the context provided."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<context_data>\n{request.context}\n</context_data>\n\nQuestion:\n{request.prompt}" if request.context else request.prompt}
        ]
        
        if request.images:
             messages[-1]["images"] = request.images
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "format": request.response_format, # Support for "json" mode
            "options": {
                "temperature": request.temperature or self.settings.llm_temperature,
                "num_ctx": self.settings.llm_context_length,
                "num_predict": request.max_tokens or self.settings.llm_max_tokens,
                "stop": request.stop_sequences
            }
        }
        
        # [Deep Audit Fix] Pass tools if provided
        if request.tools:
            payload["tools"] = request.tools
            # Note: Ollama expects tools in OpenAI format. 
            # We assume request.tools is already in correct format or dict.
            
        return payload

    @retry(exceptions=(httpx.ConnectError, httpx.TimeoutException), tries=3, delay=0.5)
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate response via Ollama Chat API (Async)."""
        url = f"{self.base_url}/api/chat"
        payload = self._build_request_payload(request, stream=False)
        
        try:
            res = await self.client.post(url, json=payload)
            if res.status_code != 200:
                raise Exception(f"Ollama API Error: {res.text}")
                
            data = res.json()
            return LLMResponse(
                text=data['message']['content'],
                tokens_used=data.get('eval_count', 0),
                model_name=self.model_name,
                finish_reason=data.get('done_reason', 'stop')
            )
        except Exception as e:
            logger.error(f"Ollama Generate Failed: {e}")
            raise

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """Stream response via Ollama Chat API (Async)."""
        url = f"{self.base_url}/api/chat"
        payload = self._build_request_payload(request, stream=True)
        
        # Smart Retry Logic for Streaming
        max_retries = 3
        
        for attempt in range(max_retries):
            tokens_yielded = False
            try:
                # We must use a new request for streaming to handle the context manager correctly
                # httpx clients are thread/async safe for multiple requests
                async with self.client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        content = await response.read()
                        raise Exception(f"Ollama API Error: {content.decode()}")
                        
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                msg = data.get('message', {})
                                content = msg.get('content', '')
                                
                                done = data.get('done', False)
                                usage = None
                                finish_reason = None
                                
                                if done:
                                    usage = data.get('eval_count', 0)
                                    finish_reason = data.get('done_reason', 'stop')
                                
                                yield LLMResponse(
                                    text=content,
                                    tokens_used=usage,
                                    model_name=self.model_name,
                                    finish_reason=finish_reason
                                )
                                tokens_yielded = True
                            except json.JSONDecodeError:
                                logger.warning(f"Ollama Stream: Dropping malformed JSON line: {line}")
                                pass
                
                # If we successfully finished the stream, break retry loop
                return
                                
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if tokens_yielded:
                    # Connection died MID-STREAM. 
                    # We cannot retry transparently. We must raise.
                    logger.error(f"Ollama Stream Failed MID-STREAM: {e}")
                    raise
                
                # Connection failed BEFORE start. Safe to retry.
                logger.warning(f"Ollama Stream Connection Failed (Attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
                
                # Exponential Backoff
                await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.error(f"Ollama Stream Failed: {e}")
                raise

    def get_model_info(self) -> Dict[str, str]:
        return {
            "provider": "Ollama",
            "model_name": self.model_name,
            "status": "connected"
        }

    async def cleanup(self) -> None:
        """Clean up resources asynchronously."""
        if self.client:
            await self.client.aclose()
            logger.info("Ollama adapter client closed")

"""
Mistral-3B quantized adapter for development environment.
Follows Liskov Substitution Principle - can be substituted for any BaseLLMAdapter.
"""
import os
from typing import Dict, Optional
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from loguru import logger

try:
    from llama_cpp import Llama
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False

from app.infrastructure.llm.base import BaseLLMAdapter, LLMRequest, LLMResponse
from app.core.config import get_settings


class LocalLLMAdapter(BaseLLMAdapter):
    """
    Adapter for Local LLMs (Llama, Mistral, etc.) via GGUF (llama-cpp-python) or Transformers.
    Handles loading, generation, and streaming.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """Initialize Mistral-3B adapter."""
        self.settings = get_settings()
        self.model_path = model_path or self.settings.llm_model_path
        self.tokenizer = None
        self.model = None
        self._is_loaded = False
        
        if self.model_path:
            self._load_model()
    
    def _load_model(self) -> None:
        """Load the model (GGUF or Transformers)."""
        try:
            logger.info(f"Loading model from {self.model_path}")
            
            if self.model_path.endswith(".gguf"):
                if not os.path.exists(self.model_path):
                    raise FileNotFoundError(f"Model file not found: {self.model_path}")
                
                if not HAS_LLAMA_CPP:
                    raise ImportError("llama-cpp-python is required for GGUF models")
                
                self.model = Llama(
                    model_path=self.model_path,
                    n_ctx=self.settings.llm_context_length,
                    n_gpu_layers=-1,  # Use all layers on GPU/Metal if available
                    verbose=False
                )
                self._is_loaded = True
                logger.info("GGUF model loaded successfully")
                return

            # Transformers loading logic
            # Configure quantization
            quantization_config = None
            if self.settings.llm_quantization == "4bit":
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )
            elif self.settings.llm_quantization == "8bit":
                quantization_config = BitsAndBytesConfig(
                    load_in_8bit=True
                )
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load model with quantization
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                quantization_config=quantization_config,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype=torch.float16 if quantization_config is None else None
            )
            
            self.model.eval()  # Set to evaluation mode
            self._is_loaded = True
            logger.info("Mistral-3B model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load Mistral-3B model: {e}")
            self._is_loaded = False
            raise
    
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")
        
        try:
            # Construct full prompt
            full_prompt = request.prompt
            if request.context:
                full_prompt = f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}\n\nAnswer:"
            
            # GGUF Generation
            if hasattr(self, 'model') and isinstance(self.model, Llama):
                max_tokens = request.max_tokens or self.settings.llm_max_tokens
                temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
                
                # Construct messages for chat completion
                system_prompt = request.system_prompt or (
                    "You are an intelligent, strictly grounded AI assistant. "
                    "Your goal is to answer the user's question using ONLY the provided Context. "
                    "1. **Grounding**: Do NOT use your own training data for facts. Use values and procedures from the Context ONLY. "
                    "2. **Intent Understanding**: You MAY use your general knowledge to UNDERSTAND the user's question (e.g., synonyms, intent), but the ANSWER must come from Context. "
                    "3. **Completeness**: If the Context has partial info, provide it. If it has nothing relevant, say: 'I cannot find the answer in the provided documents.' "
                    "4. **Formatting**: Use Markdown and clear structure. "
                    "5. **Refusal**: Do not make up answers. If the context is empty or irrelevant, refuse politely."
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}"}
                ]
                
                output = self.model.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=request.stop_sequences or [],
                )
                logger.debug(f"Llama output keys: {output.keys()}")
                
                choice = output['choices'][0]
                text = choice['message']['content']
                tokens_used = output['usage']['total_tokens']
                finish_reason = choice['finish_reason']
                
                return LLMResponse(
                    text=text.strip(),
                    tokens_used=tokens_used,
                    model_name="mistral-gguf",
                    finish_reason=finish_reason
                )

            # Transformers Generation
            # Tokenize
            inputs = self.tokenizer(
                full_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.settings.llm_context_length - 100  # Reserve space for response
            ).to(self.model.device)
            
            # Generation parameters
            max_tokens = request.max_tokens or self.settings.llm_max_tokens
            temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
            
            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    do_sample=temperature > 0,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    stop_strings=request.stop_sequences if request.stop_sequences else None
                )
            
            # Decode
            generated_text = self.tokenizer.decode(
                outputs[0][inputs['input_ids'].shape[1]:],
                skip_special_tokens=True
            )
            
            return LLMResponse(
                text=generated_text.strip(),
                tokens_used=tokens_used,
                model_name="mistral-3b-quantized",
                finish_reason="stop"
            )
            
        except Exception as e:
            logger.error(f"Error during generation: {e}")
            raise

    def stream(self, request: LLMRequest):
        """Stream text generation."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")
            
        try:
            # Construct full prompt (same logic as generate)
            full_prompt = request.prompt
            if request.context:
                full_prompt = f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}\n\nAnswer:"
                
            # GGUF Streaming
            if hasattr(self, 'model') and isinstance(self.model, Llama):
                max_tokens = request.max_tokens or self.settings.llm_max_tokens
                temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
                
                system_prompt = request.system_prompt or (
                    "You are an intelligent, strictly grounded AI assistant. "
                    "Your goal is to answer the user's question using ONLY the provided Context. "
                    "1. **Grounding**: Do NOT use your own training data for facts. Use values and procedures from the Context ONLY. "
                    "2. **Intent Understanding**: You MAY use your general knowledge to UNDERSTAND the user's question (e.g., synonyms, intent), but the ANSWER must come from Context. "
                    "3. **Completeness**: If the Context has partial info, provide it. If it has nothing relevant, say: 'I cannot find the answer in the provided documents.' "
                    "4. **Formatting**: Use Markdown and clear structure. "
                    "5. **Refusal**: Do not make up answers. If the context is empty or irrelevant, refuse politely."
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}"}
                ]
                
                stream = self.model.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=request.stop_sequences or [],
                    stream=True
                )
                
                for chunk in stream:
                    delta = chunk['choices'][0]['delta']
                    if 'content' in delta:
                        yield delta['content']
                return

            # Transformers Streaming
            from transformers import TextIteratorStreamer
            from threading import Thread
            
            streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
            
            inputs = self.tokenizer(
                full_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.settings.llm_context_length - 100
            ).to(self.model.device)
            
            generation_kwargs = dict(
                inputs,
                streamer=streamer,
                max_new_tokens=request.max_tokens or self.settings.llm_max_tokens,
                temperature=request.temperature if request.temperature is not None else self.settings.llm_temperature,
                do_sample=request.temperature > 0,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                stop_strings=request.stop_sequences if request.stop_sequences else None
            )
            
            thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
            thread.start()
            
            for new_text in streamer:
                yield new_text
                
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            raise
    
    def get_model_info(self) -> Dict[str, str]:
        """Get model information."""
        return {
            "provider": "Llama-3.2",
            "model_name": "Llama-3.2-3B-Instruct-Q4_K_M",
            "quantization": self.settings.llm_quantization,
            "context_length": str(self.settings.llm_context_length),
            "status": "loaded" if self._is_loaded else "not_loaded"
        }
    
    def is_available(self) -> bool:
        """Check if model is available."""
        return self._is_loaded and self.model is not None and self.tokenizer is not None
    
    def cleanup(self) -> None:
        """Clean up model resources."""
        if self.model:
            del self.model
            self.model = None
        if self.tokenizer:
            del self.tokenizer
            self.tokenizer = None
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
        self._is_loaded = False
        logger.info("Llama-3.2 model cleaned up")





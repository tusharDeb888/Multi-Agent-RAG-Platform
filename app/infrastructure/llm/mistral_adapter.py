"""
Mistral-3B quantized adapter for development environment.
Follows Liskov Substitution Principle - can be substituted for any BaseLLMAdapter.
"""
import os
from typing import Dict, Optional, AsyncIterator
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from loguru import logger
import asyncio

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
        
        self._lock = asyncio.Lock()
        
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
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text (Async wrapper around sync models)."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")
            
        async with self._lock:
            # Offload compute-heavy generation to thread
            return await asyncio.to_thread(self._generate_sync, request)

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        """Internal synchronous generation logic."""
        try:
            # Construct full prompt
            full_prompt = request.prompt
            if request.context:
                full_prompt = f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}\n\nAnswer:"
            
            # GGUF Generation
            if hasattr(self, 'model') and isinstance(self.model, Llama):
                max_tokens = request.max_tokens or self.settings.llm_max_tokens
                temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
                
                system_prompt = request.system_prompt or (
                    "You are an intelligent AI."
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
                
                choice = output['choices'][0]
                model_name = os.path.basename(self.model_path) if self.model_path else "local-llm"
                return LLMResponse(
                    text=choice['message']['content'].strip(),
                    tokens_used=output['usage']['total_tokens'],
                    model_name=model_name,
                    finish_reason=choice['finish_reason']
                )

            # Transformers Generation
            
            # Prepare messages ensuring system prompt is included
            system_prompt = request.system_prompt or "You are a helpful AI."
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}"}
            ]
            
            # Apply chat template (Critical for Instruct models)
            full_prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            
            inputs = self.tokenizer(
                full_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.settings.llm_context_length - 100
            ).to(self.model.device)
            
            max_tokens = request.max_tokens or self.settings.llm_max_tokens
            temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
            
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
            
            generated_text = self.tokenizer.decode(
                outputs[0][inputs['input_ids'].shape[1]:],
                skip_special_tokens=True
            )
            
            model_name = os.path.basename(self.model_path) if self.model_path else "local-llm"
            return LLMResponse(
                text=generated_text.strip(),
                tokens_used=-1, # Not easily tracked in transformers simple gen
                model_name=model_name,
                finish_reason="stop"
            )
            
        except Exception as e:
            logger.error(f"Error during generation: {e}")
            raise

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """Stream text generation (Async iterable)."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")
            
        # Lock during the entire stream to prevent VRAM contention
        # This means only one user can stream from Local LLM at a time.
        async with self._lock:
            # 1. GGUF Streaming (Async wrapper)
            if hasattr(self, 'model') and isinstance(self.model, Llama):
             # GGUF's create_chat_completion returns a sync generator.
             # We must iterate it in a thread to avoid blocking loop.
             
             # Create the generator (NOTE: this call might be fast, but iteration is slow)
             # We run the creation in a thread too to be safe.
             generator = await asyncio.to_thread(self._create_gguf_generator, request)
             
             # Iterate async
             def _safe_next(iterator):
                 try:
                     return next(iterator)
                 except StopIteration:
                     return None
                 except Exception as e:
                     raise e

             while True:
                 try:
                     chunk = await asyncio.to_thread(_safe_next, generator)
                     
                     if chunk is None:
                         break
                     
                     # Extract data
                     delta = chunk['choices'][0]['delta']
                     content = delta.get('content', '')
                     
                     # Llama-cpp-python usage in last chunk? 
                     # Often not present in stream chunks until finish.
                     # We wrap in LLMResponse
                     model_name = os.path.basename(self.model_path) if self.model_path else "local-llm"
                     yield LLMResponse(
                         text=content,
                         tokens_used=None, # Usage tracking in stream difficult for wrappers
                         model_name=model_name,
                         finish_reason=chunk['choices'][0].get('finish_reason')
                     )
                 except Exception as e:
                     logger.error(f"GGUF Stream Error: {e}")
                     # If it's a critical error, we might yield an error chunk or break
                     # For now, let's break to avoid infinite loop on error
                     yield LLMResponse(text=f"[Error: {e}]", finish_reason='error')
                     break
             return
             return

        # 2. Transformers Streaming
        # The existing logic uses a Thread and a Queue (TextIteratorStreamer).
        # We just need to wrap the queue polling.
        
        from transformers import TextIteratorStreamer
        from threading import Thread
        
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        # Launch generation in background thread (Compute bound)
        thread = Thread(target=self._run_transformers_generation, args=(request, streamer))
        thread.start()
        
        # Poll the streamer queue without blocking async loop
        # TextIteratorStreamer is an iterator that blocks on next().
        # We wrap next() in to_thread.
        
        while True:
            try:
                new_text = await asyncio.to_thread(next, streamer)
                yield LLMResponse(
                    text=new_text,
                    model_name="mistral-local",
                    tokens_used=None
                )
            except StopIteration:
                break
            except Exception as e:
                logger.error(f"Transformers Stream Error: {e}")
                raise

    def _create_gguf_generator(self, request):
        """Helper to create GGUF generator sync."""
        max_tokens = request.max_tokens or self.settings.llm_max_tokens
        temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
        
        system_prompt = request.system_prompt or "You are a helpful AI."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}"}
        ]
        
        return self.model.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=request.stop_sequences or [],
            stream=True
        )

    def _run_transformers_generation(self, request, streamer):
        """Helper target for Thread."""
        try:
            # Prepare messages
            system_prompt = request.system_prompt or "You are a helpful AI."
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{request.context}\n\nQuestion:\n{request.prompt}"}
            ]
            
            # Apply chat template
            full_prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
                
            inputs = self.tokenizer(
                full_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.settings.llm_context_length - 100
            ).to(self.model.device)
            
            max_tokens = request.max_tokens or self.settings.llm_max_tokens
            temperature = request.temperature if request.temperature is not None else self.settings.llm_temperature
            
            self.model.generate(
                **inputs,
                streamer=streamer,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                stop_strings=request.stop_sequences if request.stop_sequences else None
            )
        except Exception as e:
            logger.error(f"Threaded Generation Failed: {e}")
            # Streamer might block forever if we crash? 
            # We must ensure the streamer is terminated to unblock the consumer.
            pass
        finally:
            if streamer:
                streamer.end()
    
    def get_model_info(self) -> Dict[str, str]:
        """Get model information."""
        return {
            "provider": "Local (GGUF/Transformers)",
            "model_path": self.model_path,
            "quantization": self.settings.llm_quantization,
            "context_length": str(self.settings.llm_context_length),
            "status": "loaded" if self._is_loaded else "not_loaded"
        }
    
    def is_available(self) -> bool:
        """Check if model is available."""
        return self._is_loaded and self.model is not None
    
    async def cleanup(self) -> None:
        """Clean up model resources."""
        # Use a lock to ensure no generation is happening while cleaning up
        async with self._lock:
            if self.model:
                del self.model
                self.model = None
            if self.tokenizer:
                del self.tokenizer
                self.tokenizer = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                torch.mps.empty_cache()
            
            self._is_loaded = False
            logger.info(f"{self.settings.llm_provider} model cleaned up")





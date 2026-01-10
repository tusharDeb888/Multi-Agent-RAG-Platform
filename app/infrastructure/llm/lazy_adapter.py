"""
Lazy LLM Adapter for VRAM optimization.
Wraps a real adapter and loads it only on demand, unloading it after an idle timeout.
"""
import asyncio
from typing import Optional, Callable, Dict, Any, AsyncIterator
import time
from loguru import logger

from app.infrastructure.llm.base import BaseLLMAdapter, LLMRequest, LLMResponse
from app.core.config import get_settings

class LazyLLMAdapter(BaseLLMAdapter):
    """
    Proxy adapter that loads the real LLM only when needed and unloads it after a timeout.
    """
    
    def __init__(self, factory_func: Callable[[], BaseLLMAdapter]):
        """
        Initialize Lazy Adapter.
        
        Args:
            factory_func: Function that returns the REAL adapter instance.
        """
        self.settings = get_settings()
        self._factory = factory_func
        self._delegate: Optional[BaseLLMAdapter] = None
        self._unload_task: Optional[asyncio.Task] = None
        self._last_access = 0.0
        self._lock = asyncio.Lock()
        
        logger.info(f"LazyLLMAdapter initialized. Idle timeout: {self.settings.llm_idle_timeout}s")

    async def _ensure_loaded(self):
        """Ensure the real model is loaded."""
        async with self._lock:
            # Cancel pending unload if any
            if self._unload_task and not self._unload_task.done():
                self._unload_task.cancel()
                try:
                    await self._unload_task
                except asyncio.CancelledError:
                    pass
                self._unload_task = None

            if self._delegate is None:
                logger.info("LazyLLM: Loading real model on demand...")
                t0 = time.time()
                # Run factory (might be sync or async, but factory logic in this codebase is sync)
                # If factory is heavy, should ideally be thread-offloaded, but factory.py creates object sync.
                # The model *loading* happens in __init__ of the adapter usually.
                try:
                    self._delegate = await asyncio.to_thread(self._factory)
                    logger.info(f"LazyLLM: Model loaded in {time.time() - t0:.2f}s")
                except Exception as e:
                    logger.error(f"LazyLLM: Failed to load model: {e}")
                    raise
            
            self._last_access = time.time()

    def _schedule_unload(self):
        """Schedule the unload task based on timeout settings."""
        timeout = self.settings.llm_idle_timeout
        if timeout < 0:
            return  # Never unload
            
        if self._unload_task and not self._unload_task.done():
            # Existing task is fine? No, we need to reset the timer.
            # Easiest way is to cancel and spawn new.
            # But verifying if we can just let existing one run and check timestamp is better?
            # Let's spawn a watcher that checks periodically or sleeps once? 
            # Simple approach: Sleep(timeout) then check if (now - last_access >= timeout).
            self._unload_task.cancel()
            
        self._unload_task = asyncio.create_task(self._unload_loop(timeout))

    async def _unload_loop(self, timeout: int):
        """Wait for timeout and unload if idle."""
        try:
            while True:
                # Calculate time to sleep
                now = time.time()
                elapsed = now - self._last_access
                remaining = timeout - elapsed
                
                if remaining <= 0:
                    # Time to unload
                    break
                
                await asyncio.sleep(remaining)
            
            # Unload
            await self.cleanup()
            
        except asyncio.CancelledError:
            # Task cancelled (new request came in)
            pass
        except Exception as e:
            logger.error(f"LazyLLM: Unload task error: {e}")

    async def cleanup(self) -> None:
        """Unload the model and free VRAM."""
        async with self._lock:
            if self._delegate:
                logger.info("LazyLLM: Unloading model due to idle timeout...")
                await self._delegate.cleanup()
                self._delegate = None
                
                # Force garbage collection
                import gc
                gc.collect()
                logger.info("LazyLLM: Model unloaded.")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Delegate generation."""
        await self._ensure_loaded()
        try:
            if not self._delegate: raise RuntimeError("Delegate failed to load")
            return await self._delegate.generate(request)
        finally:
            self._last_access = time.time()
            self._schedule_unload()

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """Delegate streaming."""
        await self._ensure_loaded()
        try:
            if not self._delegate: raise RuntimeError("Delegate failed to load")
            async for chunk in self._delegate.stream(request):
                yield chunk
        finally:
            self._last_access = time.time()
            self._schedule_unload()

    def get_model_info(self) -> Dict[str, str]:
        if self._delegate:
            info = self._delegate.get_model_info()
            info['mode'] = 'lazy (loaded)'
            return info
        return {
            "provider": "lazy",
            "mode": "lazy (unloaded)",
            "status": "unloaded"
        }

    async def is_available(self) -> bool:
        # If unloaded, we are technically "available" to load.
        # But health check might want to know if backend works.
        # For lazy, we return True if configured correctly.
        return True 

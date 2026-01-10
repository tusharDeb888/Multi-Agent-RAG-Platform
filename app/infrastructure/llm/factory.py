"""
LLM Factory for creating appropriate LLM adapters.
Follows Factory Pattern and Dependency Inversion Principle.
"""
from typing import Optional
from loguru import logger

from app.infrastructure.llm.base import BaseLLMAdapter
from app.infrastructure.llm.mistral_adapter import LocalLLMAdapter
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.core.config import get_settings, LLMProvider


class LLMFactory:
    """
    Factory for creating LLM adapters based on configuration.
    Follows Open/Closed Principle - open for extension, closed for modification.
    """
    
    _instance: Optional[BaseLLMAdapter] = None
    
    @staticmethod
    def create_llm_adapter() -> BaseLLMAdapter:
        """
        Create LLM adapter based on configuration.
        
        Returns:
            LLM adapter instance
            
        Raises:
            ValueError: If provider is not supported
        """
        settings = get_settings()
        
        # Return singleton instance if already created
        if LLMFactory._instance is not None:
            return LLMFactory._instance
        
        logger.info(f"Creating LLM adapter for provider: {settings.llm_provider}")
        
        # Helper to create the actual adapter (Synchronous creation)
        def _create_real_adapter() -> BaseLLMAdapter:
            if settings.llm_provider in [LLMProvider.LLAMA_3_2, LLMProvider.LOCAL]:
                return LocalLLMAdapter()
            elif settings.llm_provider == LLMProvider.OLLAMA:
                return OllamaAdapter()
            elif settings.llm_provider == LLMProvider.LLAMA2:
                # TODO: Implement Llama2Adapter
                raise NotImplementedError("Llama2 adapter not yet implemented")
            elif settings.llm_provider == LLMProvider.QWEN:
                # TODO: Implement QwenAdapter
                raise NotImplementedError("Qwen adapter not yet implemented")
            elif settings.llm_provider == LLMProvider.CUSTOM:
                # TODO: Implement CustomAdapter
                raise NotImplementedError("Custom adapter not yet implemented")
            else:
                raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

        # Lazy vs Eager Loading
        if settings.lazy_load_llm:
            from app.infrastructure.llm.lazy_adapter import LazyLLMAdapter
            logger.info("Lazy Loading enabled: Model will load on first request.")
            LLMFactory._instance = LazyLLMAdapter(factory_func=_create_real_adapter)
        else:
            LLMFactory._instance = _create_real_adapter()
        
        return LLMFactory._instance
    
    @staticmethod
    def reset() -> None:
        """Reset the factory (useful for testing)."""
        # Note: cleanup() is now async, so strict reset in sync context is hard.
        # This is mostly for tests.
        LLMFactory._instance = None

    @staticmethod
    async def shutdown() -> None:
        """Gracefully shutdown the LLM adapter."""
        if LLMFactory._instance:
            await LLMFactory._instance.cleanup()
        LLMFactory._instance = None

    @staticmethod
    async def warmup() -> None:
        """Explicitly load the LLM model to avoid cold start on first request."""
        if LLMFactory._instance is None:
            logger.info("Warming up LLM...")
            # Create instance
            adapter = LLMFactory.create_llm_adapter()
            
            # If Lazy, we must force load it now
            if hasattr(adapter, "_ensure_loaded"):
                await adapter._ensure_loaded()
            
            # Health Check (Async)
            logger.info("Checking LLM availability...")
            if not await adapter.is_available():
                msg = f"LLM Adapter created but backend ({adapter.get_model_info().get('provider')}) is seemingly unavailable."
                logger.warning(msg)
                # We raise exception to trigger the retry loop in main.py
                raise RuntimeError(msg)
                
            logger.info(f"LLM warmed up and ready: {adapter.get_model_info()}")
        else:
            logger.info("LLM already loaded.")





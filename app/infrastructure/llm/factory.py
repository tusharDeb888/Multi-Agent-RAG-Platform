"""
LLM Factory for creating appropriate LLM adapters.
Follows Factory Pattern and Dependency Inversion Principle.
"""
from typing import Optional
from loguru import logger

from app.infrastructure.llm.base import BaseLLMAdapter
from app.infrastructure.llm.mistral_adapter import LocalLLMAdapter
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
        
        if settings.llm_provider in [LLMProvider.LLAMA_3_2, LLMProvider.LOCAL]:
            LLMFactory._instance = LocalLLMAdapter()
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
        
        return LLMFactory._instance
    
    @staticmethod
    def reset() -> None:
        """Reset the factory (useful for testing)."""
        if LLMFactory._instance:
            LLMFactory._instance.cleanup()
        LLMFactory._instance = None

    @staticmethod
    def warmup() -> None:
        """Explicitly load the LLM model to avoid cold start on first request."""
        if LLMFactory._instance is None:
            logger.info("Warming up LLM...")
            LLMFactory.create_llm_adapter()
        else:
            logger.info("LLM already loaded.")





"""
Base LLM interface following Interface Segregation Principle.
All LLM implementations must adhere to this contract.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from pydantic import BaseModel


class LLMRequest(BaseModel):
    """Request model for LLM generation."""
    prompt: str
    context: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    system_prompt: Optional[str] = None


class LLMResponse(BaseModel):
    """Response model from LLM generation."""
    text: str
    tokens_used: Optional[int] = None
    model_name: Optional[str] = None
    finish_reason: Optional[str] = None


class BaseLLMAdapter(ABC):
    """
    Abstract base class for LLM adapters.
    Follows Dependency Inversion Principle - high-level modules depend on this abstraction.
    """
    
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text from the LLM.
        
        Args:
            request: LLM request with prompt and parameters
            
        Returns:
            LLM response with generated text
        """
        pass

    @abstractmethod
    def stream(self, request: LLMRequest) -> "Iterator[str]":
        """
        Stream generated text from the LLM.
        
        Args:
            request: LLM request with prompt and parameters
            
        Yields:
             Generated text chunks
        """
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, str]:
        """
        Get information about the loaded model.
        
        Returns:
            Dictionary with model information
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the LLM is available and ready.
        
        Returns:
            True if available, False otherwise
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources."""
        pass





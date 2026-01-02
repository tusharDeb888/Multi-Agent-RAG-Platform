from abc import ABC, abstractmethod
from typing import Optional

class BaseVisionAdapter(ABC):
    """Abstract base class for Vision Adapters."""
    
    @abstractmethod
    def describe_image(self, image_data: bytes) -> str:
        """
        Generate a textual description of an image.
        
        Args:
            image_data: Raw bytes of the image
            
        Returns:
            String description/caption of the image
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the adapter is configured and ready."""
        pass

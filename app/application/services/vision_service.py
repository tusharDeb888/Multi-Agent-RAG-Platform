from typing import Optional
from loguru import logger
from app.core.config import get_settings
from app.infrastructure.vision.base import BaseVisionAdapter
from app.infrastructure.vision.local_adapter import LocalVisionAdapter
from app.infrastructure.vision.ollama_adapter import OllamaVisionAdapter

class VisionService:
    """
    Service for Multimodal Vision capabilities.
    Acts as a facade/factory for underlying adapters.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.adapter: Optional[BaseVisionAdapter] = None
        self._initialize_adapter()
        
    def _initialize_adapter(self):
        provider = self.settings.vision_provider.lower()
        
        if provider == "ollama":
            logger.info("Initializing Ollama Vision Adapter")
            self.adapter = OllamaVisionAdapter()
        elif provider == "local":
            logger.info("Initializing Local Vision Adapter")
            self.adapter = LocalVisionAdapter()
        else:
            logger.warning(f"Unknown vision provider: {provider}")
            
    def describe_image(self, image_data: bytes) -> str:
        """
        Generate description for an image.
        """
        if not self.adapter:
            return "Vision service not initialized."
            
        if not self.adapter.is_available():
            return "Vision model unavailable (check API key or model path)."
            
        return self.adapter.describe_image(image_data)

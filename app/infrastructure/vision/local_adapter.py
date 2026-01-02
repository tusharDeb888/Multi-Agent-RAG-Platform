from loguru import logger
from app.infrastructure.vision.base import BaseVisionAdapter

class LocalVisionAdapter(BaseVisionAdapter):
    """
    Local Vision Adapter (e.g., LLaVA, Moondream, Qwen-VL).
    Uses local GGUF models via llama-cpp-python.
    """
    
    def __init__(self):
        logger.warning("Local Vision Adapter is a placeholder for now.")
        
    def is_available(self) -> bool:
        # TODO: Check if model file exists
        return True
        
    def describe_image(self, image_data: bytes) -> str:
        return "[Local Vision]: Image description feature coming soon (requires model download)."

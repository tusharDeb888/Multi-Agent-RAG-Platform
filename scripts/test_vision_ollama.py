
import os
import sys
import logging
from PIL import Image
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.getcwd())

from app.application.services.vision_service import VisionService
from app.core.config import get_settings

def test_ollama():
    logger.info("Testing Vision Service (Ollama)...")
    
    settings = get_settings()
    logger.info(f"Provider: {settings.vision_provider}")
    logger.info(f"Ollama URL: {settings.ollama_base_url}")
    logger.info(f"Model: {settings.vision_model_name}")
    
    # Create a simple dummy image (blue square)
    img = Image.new('RGB', (100, 100), color = 'blue')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()
    
    service = VisionService()
    
    logger.info("Requesting description...")
    description = service.describe_image(img_bytes)
    
    logger.info(f"Result: {description}")

if __name__ == "__main__":
    test_ollama()

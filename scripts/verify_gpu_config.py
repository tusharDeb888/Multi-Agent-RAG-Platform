import sys
import os
from loguru import logger

# Add app to path
sys.path.append(os.getcwd())

from app.core.config import get_settings
from app.infrastructure.embeddings.embedding_service import EmbeddingService

def verify_device():
    settings = get_settings()
    logger.info(f"Configured Device: {settings.embedding_device}")
    
    service = EmbeddingService()
    model_device = str(service.model.device)
    logger.info(f"Loaded Model Device: {model_device}")
    
    if settings.embedding_device in model_device or (settings.embedding_device == "cpu" and "cpu" in model_device):
        logger.info("✅ Verification PASSED: Model loaded on correct device.")
    else:
        logger.error(f"❌ Verification FAILED: Expected {settings.embedding_device}, got {model_device}")

if __name__ == "__main__":
    verify_device()

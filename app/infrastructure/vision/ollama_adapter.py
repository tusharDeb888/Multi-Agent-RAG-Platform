import base64
import requests
import io
from loguru import logger
from typing import Optional
from app.core.config import get_settings
from app.infrastructure.vision.base import BaseVisionAdapter

class OllamaVisionAdapter(BaseVisionAdapter):
    """
    Vision adapter using Ollama locally.
    Connects to Ollama API (default: http://localhost:11434).
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.ollama_base_url
        self.model_name = self.settings.vision_model_name
        self.api_url = f"{self.base_url}/api/generate"
        
    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = requests.get(self.base_url, timeout=2)
            return response.status_code == 200
        except Exception:
            return False
        
    def describe_image(self, image_data: bytes) -> str:
        """
        Generate description using Ollama.
        """
        # Encode image to base64
        try:
            b64_image = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "model": self.model_name,
                "prompt": "Describe this image in detail, focusing on any charts, data trends, or text visible.",
                "images": [b64_image],
                "stream": False
            }
            
            logger.info(f"Sending image to Ollama ({self.model_name})...")
            response = requests.post(self.api_url, json=payload, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"Ollama API Error {response.status_code}: {response.text}")
                return f"Error: Ollama returned {response.status_code}"
                
            result = response.json()
            description = result.get("response", "").strip()
            
            if description:
                logger.info(f"Image described: {description[:50]}...")
                return description
            else:
                return "Ollama returned empty description."
                
        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to Ollama. Is it running?")
            return "Error: Ollama not reachable."
        except Exception as e:
            logger.error(f"Ollama vision error: {e}")
            return "Error processing image with Ollama."

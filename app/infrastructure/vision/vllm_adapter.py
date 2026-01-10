import base64
import requests
from loguru import logger
from typing import Optional
from app.core.config import get_settings
from app.infrastructure.vision.base import BaseVisionAdapter

class VllmVisionAdapter(BaseVisionAdapter):
    """
    Vision adapter using vLLM (OpenAI-compatible credentials).
    Connects to vLLM API (default: http://vllm:8000/v1).
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.vllm_base_url
        self.model_name = self.settings.vision_model_name
        self.api_url = f"{self.base_url}/chat/completions"
        self._check_connection()

    def _check_connection(self):
        """Initial connection check."""
        try:
            # Check models endpoint
            resp = requests.get(f"{self.base_url}/models", timeout=2)
            if resp.status_code == 200:
                logger.info(f"Connected to vLLM at {self.base_url}")
            else:
                logger.warning(f"vLLM responded with {resp.status_code}")
        except Exception as e:
            logger.warning(f"Could not connect to vLLM at {self.base_url}: {e}")

    def is_available(self) -> bool:
        """Check if vLLM is running."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2) # vLLM health endpoint
            return response.status_code == 200
        except Exception:
            return False

    def _generate(self, prompt: str, image_data: bytes) -> str:
        """Helper to call vLLM Chat Completions API."""
        try:
            # vLLM expects format "data:image/jpeg;base64,{base64_string}"
            # assuming jpeg for simplicity or auto-detect
            b64_image = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{b64_image}"

            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.1
            }

            logger.info(f"Sending image to vLLM ({self.model_name})...")
            response = requests.post(self.api_url, json=payload, timeout=60)

            if response.status_code != 200:
                logger.error(f"vLLM API Error {response.status_code}: {response.text}")
                return f"Error: vLLM returned {response.status_code}"

            result = response.json()
            # OpenAI format: choices[0].message.content
            content = result["choices"][0]["message"]["content"]
            return content.strip()

        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to vLLM. Is it running?")
            return "Error: vLLM not reachable."
        except Exception as e:
            logger.error(f"vLLM vision error: {e}")
            return "Error processing image with vLLM."

    def describe_image(self, image_data: bytes) -> str:
        """Generate description using vLLM."""
        prompt = "Describe this image in detail, focusing on any charts, data trends, or visible text."
        return self._generate(prompt, image_data)

    def transcribe_image(self, image_data: bytes) -> str:
        """Extract text using vLLM."""
        prompt = """Extract ALL text from this image character-by-character.
Rules:
- Output ONLY the text you see
- Preserve line breaks and formatting  
- Do NOT describe the image
- Do NOT add conversational filler
- If unreadable, output: [UNREADABLE]
"""
        return self._generate(prompt, image_data)

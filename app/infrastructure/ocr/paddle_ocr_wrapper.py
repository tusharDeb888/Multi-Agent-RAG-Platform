"""
PaddleOCR Wrapper - Replace Tesseract with PaddleOCR for better accuracy.

Benefits over Tesseract:
- 2-3x better accuracy on complex layouts
- Multi-language support (80+ languages)
- Better handling of rotated/skewed text
- Deep learning-based (higher quality)
"""
import numpy as np
from PIL import Image
from loguru import logger
from typing import Optional, List, Tuple


class PaddleOCRWrapper:
    """
    Singleton wrapper for PaddleOCR with lazy initialization.
    Replaces Tesseract for enterprise-grade OCR accuracy.
    """
    
    _instance = None
    _ocr_engine = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Lazy initialization - OCR engine loaded on first use."""
        pass
    
    def _ensure_loaded(self):
        """Load PaddleOCR engine on first use."""
        if self._ocr_engine is None:
            try:
                from paddleocr import PaddleOCR
                
                # Initialize with minimal settings (compatible with all PaddleOCR versions)
                import logging
                logging.getLogger("ppocr").setLevel(logging.ERROR)
                
                self._ocr_engine = PaddleOCR(
                    use_angle_cls=False,  # Disable angle cls to prevent ShapeError on Mac
                    lang='en'    # English language
                    # show_logs = True # Removed: Invalid in newer versions
                )
                logger.info("PaddleOCR engine initialized successfully")
                
            except ImportError:
                logger.error("PaddleOCR not installed. Install: pip install paddlepaddle paddleocr")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR: {e}")
                raise
    
    def image_to_string(
        self, 
        image: Image.Image, 
        config: Optional[str] = None, 
        timeout: int = 30
    ) -> str:
        """
        Extract text from PIL Image (Tesseract-compatible interface).
        
        Args:
            image: PIL Image object
            config: Ignored (for Tesseract compatibility)
            timeout: Ignored (for Tesseract compatibility)
            
        Returns:
            Extracted text string
        """
        self._ensure_loaded()
        
        try:
            # Convert PIL to numpy array (PaddleOCR expects numpy)
            if isinstance(image, Image.Image):
                # Force RGB conversion to ensure 3 channels (H, W, 3)
                # This fixes 'tuple index out of range' in internal normalization
                if image.mode != 'RGB':
                    logger.debug(f"Converting image mode from {image.mode} to RGB")
                    image = image.convert('RGB')
                img_array = np.array(image)
            else:
                img_array = image
                # If numpy array, check shape
                if isinstance(img_array, np.ndarray):
                    if len(img_array.shape) == 2:
                        logger.debug("Converting grayscale numpy array to RGB")
                        img_array = np.stack((img_array,)*3, axis=-1)
                    elif len(img_array.shape) == 3 and img_array.shape[2] == 4:
                        logger.debug("Converting RGBA numpy array to RGB")
                        img_array = img_array[:, :, :3]
            
            # Run OCR (PaddleOCR 3.3.2 API)
            # Explicitly disable angle classifier (cls=False) to prevent ShapeError on Mac
            try:
                # [Fix] Removed 'cls=False' as it causes TypeError. 'use_angle_cls' is already set in __init__.
                result = self._ocr_engine.ocr(img_array)
            except Exception as paddle_error:
                logger.warning(f"PaddleOCR failed ({paddle_error}), falling back to Tesseract.")
                try:
                    import pytesseract
                    # Use Tesseract as fallback
                    return pytesseract.image_to_string(image)
                except ImportError:
                    logger.error("pytesseract not installed. No fallback available.")
                    return ""
                except Exception as tess_error:
                    logger.error(f"Tesseract fallback failed: {tess_error}")
                    return ""
            
            # Debug logging with safe access
            logger.debug(f"PaddleOCR raw result type: {type(result)}")
            if result and isinstance(result, list) and len(result) > 0:
                logger.debug(f"PaddleOCR result length: {len(result)}")
                if result[0] is not None:
                    logger.debug(f"PaddleOCR result[0] type: {type(result[0])}")
                    if isinstance(result[0], list) and len(result[0]) > 0:
                        logger.debug(f"PaddleOCR result[0] length: {len(result[0])}")
                        logger.debug(f"First item sample: {result[0][0]}")
                else:
                    logger.debug("PaddleOCR result[0] is None")
            else:
                logger.debug(f"PaddleOCR result is empty or not a list")
            
            # Extract text from result structure
            if not result:
                logger.debug("PaddleOCR returned empty result")
                return ""
            
            lines = []
            try:
                # PaddleOCR 3.3.2 returns: [page_results]
                # page_results = [[bbox_coords, (text, confidence)], ...] or None
                
                if not isinstance(result, list):
                    logger.warning(f"Unexpected result type: {type(result)}")
                    return ""
                
                # Get first page results
                page_result = result[0] if len(result) > 0 else None
                
                if page_result is None:
                    logger.debug("No text detected on page")
                    return ""
                
                if not isinstance(page_result, list):
                    logger.warning(f"Unexpected page_result type: {type(page_result)}")
                    return ""
                
                # Parse each detection
                for detection in page_result:
                    if not detection or not isinstance(detection, list):
                        continue
                    
                    # Each detection: [bbox, (text, confidence)]
                    # bbox is usually a list of 4 points
                    # text_info is a tuple (text, confidence)
                    
                    if len(detection) < 2:
                        logger.debug(f"Detection has insufficient elements: {len(detection)}")
                        continue
                    
                    # Get text info (should be at index 1)
                    text_info = detection[1]
                    
                    if not text_info:
                        continue
                    
                    # Handle different text_info formats
                    if isinstance(text_info, tuple):
                        if len(text_info) >= 2:
                            text, confidence = text_info[0], text_info[1]
                            # Filter low-confidence results
                            if isinstance(confidence, (int, float)) and confidence > 0.5:
                                lines.append(str(text))
                        elif len(text_info) == 1:
                            # Sometimes just text without confidence
                            lines.append(str(text_info[0]))
                    elif isinstance(text_info, str):
                        # Direct string
                        lines.append(text_info)
                    elif isinstance(text_info, list) and len(text_info) >= 2:
                        # Sometimes returned as list instead of tuple
                        text, confidence = text_info[0], text_info[1]
                        if isinstance(confidence, (int, float)) and confidence > 0.5:
                            lines.append(str(text))
                
                result_text = "\n".join(lines)
                logger.debug(f"PaddleOCR extracted {len(lines)} lines, {len(result_text)} total chars")
                return result_text
                
            except Exception as parse_error:
                logger.error(f"PaddleOCR result parsing failed: {parse_error}")
                logger.error(f"Result structure: {result}")
                return ""
            
        except Exception as e:
            # Fallback for outer exceptions
            logger.warning(f"PaddleOCR critical failure: {e}. Attempting Tesseract fallback.")
            try:
                import pytesseract
                return pytesseract.image_to_string(image)
            except Exception as tess_e:
                logger.error(f"Tesseract fallback also failed: {tess_e}")
                import traceback
                logger.error(traceback.format_exc())
                return ""
    
    def get_version(self) -> str:
        """Get PaddleOCR version (Tesseract-compatible interface)."""
        try:
            import paddleocr
            return paddleocr.__version__
        except:
            return "unknown"


# Global instance (Tesseract-compatible interface)
_paddle_ocr = PaddleOCRWrapper()


def image_to_string(image: Image.Image, config: str = "", timeout: int = 30) -> str:
    """
    Tesseract-compatible function signature.
    Drop-in replacement for pytesseract.image_to_string().
    """
    return _paddle_ocr.image_to_string(image, config, timeout)


def get_tesseract_version() -> str:
    """Tesseract-compatible function (returns PaddleOCR version)."""
    return _paddle_ocr.get_version()


class TesseractNotFoundError(Exception):
    """Compatibility exception for Tesseract."""
    pass

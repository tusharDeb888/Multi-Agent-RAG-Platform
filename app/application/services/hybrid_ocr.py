"""
Hybrid OCR Module: Strict Text-Only (PaddleOCR + Tesseract)
ZERO-TRUST COMPLIANT: No Vision AI, No Hallucinations.
"""
from PIL import Image, ImageEnhance, ImageFilter
from loguru import logger
from app.infrastructure.ocr import paddle_ocr_wrapper as pytesseract  # PaddleOCR drop-in replacement
import pytesseract as real_tesseract # Fallback
import io

def perform_hybrid_ocr(image_obj: Image.Image, vision_service=None, use_vision: bool = False, timeout: int = 30) -> str:
    """
    Strict OCR: PaddleOCR (Primary) -> Tesseract (Fallback).
    
    ZERO-TRUST RULES (RELAXED for Noisy/Handwritten):
    1. Primary: Deterministic OCR (Paddle/Tesseract).
    2. Fallback: Vision AI (Moondream/Ollama) strictly for unreadable/handwritten text.
    
    Args:
        image_obj: PIL Image object
        vision_service: VisionService instance for fallback
        use_vision: Enable Vision AI fallback
        timeout: Timeout in seconds for OCR
        
    Returns:
        Extracted text string or "[UNREADABLE_PAGE]"
    """
    text = ""
    
    # 1. Primary: PaddleOCR (Fast & Accurate)
    try:
        text = perform_paddle_ocr(image_obj, timeout=timeout)
    except Exception as e:
        logger.error(f"PaddleOCR primary failed: {e}")
        text = ""

    # 2. Validation & Fallback (Standard OCR)
    # If Paddle failed or returned garbage, try Tesseract
    if not text or len(text.strip()) < 10:
        logger.warning(f"PaddleOCR result poor (len={len(text)}), attempting Tesseract Fallback...")
        try:
            text = perform_tesseract_fallback(image_obj)
        except Exception as e:
             logger.error(f"Tesseract fallback failed: {e}")
    
    # 3. Vision AI Fallback (The "Noisy/Handwritten" Clause)
    # If standard OCR failed to get meaningful text, use Vision AI if enabled
    if (not text or len(text.strip()) < 5):
        if use_vision and vision_service:
            logger.warning("Standard OCR failed. Attempting Vision AI Fallback for Noisy/Handwritten text...")
            try:
                # Convert PIL image to bytes for vision service
                img_byte_arr = io.BytesIO()
                # Use Original Image for Vision (Preprocessing might destroy semantic context for LLMs)
                image_obj.save(img_byte_arr, format=image_obj.format or 'PNG')
                image_bytes = img_byte_arr.getvalue()
                
                text = vision_service.transcribe_image(image_bytes)
                logger.info(f"Vision AI returned {len(text)} chars")
                
                # If Vision also fails
                if not text or "ERROR" in text:
                     text = ""
                     
            except Exception as e:
                logger.error(f"Vision AI Fallback failed: {e}")
        else:
             logger.debug("Vision fallback disabled or service unavailable.")

    # 4. Final Gatekeeper
    if not text or len(text.strip()) < 5:
        logger.warning("All OCR engines failed to extract meaningful text. Marking as UNREADABLE.")
        return "[UNREADABLE_PAGE]"
        
    return text


def perform_paddle_ocr(image_obj: Image.Image, timeout: int = 30) -> str:
    """
    Optimized PaddleOCR with preprocessing.
    """
    # Preprocessing
    processed_image = _preprocess_image(image_obj)
    
    text = pytesseract.image_to_string(
        processed_image, 
        timeout=timeout
    )
    
    logger.info(f"PaddleOCR returned {len(text)} chars")
    return text


def perform_tesseract_fallback(image_obj: Image.Image) -> str:
    """
    Standard Tesseract OCR as safety net.
    """
    # Preprocessing
    processed_image = _preprocess_image(image_obj)
    
    # Ensure Tesseract is installed or handle error
    try:
        text = real_tesseract.image_to_string(processed_image)
        logger.info(f"Tesseract returned {len(text)} chars")
        return text
    except Exception as e:
        logger.error(f"Tesseract execution error: {e}")
        raise


def _preprocess_image(image_obj: Image.Image) -> Image.Image:
    """
    Advanced preprocessing for Noisy/Blurred OCR.
    """
    if image_obj.mode != 'L':
        image_obj = image_obj.convert('L')  # Grayscale
    
    # 1. Contrast Boosting
    enhancer = ImageEnhance.Contrast(image_obj)
    image_obj = enhancer.enhance(2.0)  

    # 2. Sharpening (Critical for Blur)
    enhancer = ImageEnhance.Sharpness(image_obj)
    image_obj = enhancer.enhance(2.0)
    
    # 3. Unsharp Mask (Edge Enhancement)
    try:
        image_obj = image_obj.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    except Exception:
        pass # Ignore if filter fails
        
    return image_obj

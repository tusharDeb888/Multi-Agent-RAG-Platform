
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
import sys
import os
sys.path.append(os.getcwd())

from app.application.services.hybrid_ocr import perform_hybrid_ocr, _preprocess_image

class TestEnhancedOCR(unittest.TestCase):
    
    def setUp(self):
        # Create a dummy image
        self.image = Image.new('RGB', (100, 30), color = (73, 109, 137))
        self.mock_vision = MagicMock()
        
    def test_preprocess_filters(self):
        """Verify preprocessing doesn't crash and returns an image."""
        try:
            processed = _preprocess_image(self.image)
            self.assertIsInstance(processed, Image.Image)
            # Check if converted to grayscale
            self.assertEqual(processed.mode, 'L')
            print("Preprocessing test passed (Filters applied)")
        except Exception as e:
            self.fail(f"Preprocessing failed: {e}")

    @patch('app.application.services.hybrid_ocr.perform_paddle_ocr')
    @patch('app.application.services.hybrid_ocr.perform_tesseract_fallback')
    def test_vision_fallback_triggers(self, mock_tess, mock_paddle):
        """Test that vision fallback is called when standard OCR fails."""
        # Setup mocks to fail standard OCR
        mock_paddle.return_value = "" 
        mock_tess.return_value = "   " # Garbage/Empty
        
        # Setup Vision Mock to succeed
        self.mock_vision.transcribe_image.return_value = "Handwritten Text Detected"
        
        # Run Hybrid OCR with use_vision=True
        result = perform_hybrid_ocr(self.image, vision_service=self.mock_vision, use_vision=True)
        
        # Verify
        self.assertEqual(result, "Handwritten Text Detected")
        self.mock_vision.transcribe_image.assert_called_once()
        print("Vision Fallback trigger test passed")

    @patch('app.application.services.hybrid_ocr.perform_paddle_ocr')
    def test_standard_ocr_success(self, mock_paddle):
        """Test standard OCR success path (Vision should NOT be called)."""
        mock_paddle.return_value = "Clear Printed Text"
        
        result = perform_hybrid_ocr(self.image, vision_service=self.mock_vision, use_vision=True)
        
        self.assertEqual(result, "Clear Printed Text")
        self.mock_vision.transcribe_image.assert_not_called()
        print("Standard OCR success path test passed")

if __name__ == '__main__':
    unittest.main()

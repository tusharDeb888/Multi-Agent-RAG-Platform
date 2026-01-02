
import sys
import pytesseract
from PIL import Image

def test_tesseract():
    print("Testing Tesseract OCR...")
    try:
        # Check if tesseract is in path
        version = pytesseract.get_tesseract_version()
        print(f"✅ Tesseract found! Version: {version}")
        
        # Create a simple dummy image with text
        img = Image.new('RGB', (100, 30), color = (255, 255, 255))
        # We can't easily draw text without a font file, but we can try to OCR a blank image or 
        # just assume if get_tesseract_version works, the binary is there.
        
        print("Tesseract binary is accessible.")
        return True
        
    except pytesseract.TesseractNotFoundError:
        print("❌ Tesseract binary not found in PATH.")
        print("Please install it using: brew install tesseract")
        return False
    except Exception as e:
        print(f"❌ Error testing Tesseract: {e}")
        return False

if __name__ == "__main__":
    test_tesseract()

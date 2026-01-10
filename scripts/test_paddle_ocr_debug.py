
import os
import sys
import logging
from PIL import Image, ImageDraw
import numpy as np
# Add project root to path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_paddle_structure():
    print("Initializing PaddleOCR...")
    try:
        from paddleocr import PaddleOCR
        # Initialize exactly as in the wrapper
        ocr_engine = PaddleOCR(
            use_angle_cls=True, 
            lang='en',
            use_gpu=False,
            show_log=False 
        )
        
        # Load the problematic PDF
        from pdf2image import convert_from_path
        pdf_path = "/Users/tushardeb/IOCL/data/uploads/1_16863750998269.pdf"
        
        if os.path.exists(pdf_path):
            print(f"Loading PDF: {pdf_path}")
            images = convert_from_path(pdf_path, first_page=1, last_page=13)
            # Log mentions page 13
            img = images[-1] 
            print(f"Loaded page 13, size: {img.size}")
        else:
            print(f"PDF not found at {pdf_path}, using empty image")
            img = Image.new('RGB', (300, 100), color=(255, 255, 255))

        img_array = np.array(img)
        
        print("\nRunning OCR on actual document page...")
        # Run OCR
        result = ocr_engine.ocr(img_array, cls=True) 
        
        print(f"\nRaw Result Type: {type(result)}")
        # print(f"Raw Result: {result}") # Limit output if huge
        
        if isinstance(result, list):
            print(f"List Length: {len(result)}")
            for i, item in enumerate(result):
                print(f"Item {i} Type: {type(item)}")
                print(f"Item {i} Value: {item}")
                if isinstance(item, list):
                    for j, subitem in enumerate(item):
                        print(f"  SubItem {j} Type: {type(subitem)}")
                        print(f"  SubItem {j} Value: {subitem}")
                        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

def test_wrapper_integration():
    print("\nTesting via Wrapper...")
    try:
        from app.infrastructure.ocr.paddle_ocr_wrapper import _paddle_ocr
        img = Image.new('RGB', (300, 100), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Wrapper Test", fill=(0, 0, 0))
        
        text = _paddle_ocr.image_to_string(img)
        print(f"Wrapper Output: '{text}'")
    except Exception as e:
        print(f"Wrapper Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # We suspect cls=True might be issue, or result structure. 
    # Let's try raw first.
    test_paddle_structure()
    test_wrapper_integration()

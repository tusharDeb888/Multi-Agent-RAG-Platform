import sys
import os
import io
import pdfplumber
from app.core.config import get_settings
from app.infrastructure.vision.ollama_adapter import OllamaVisionAdapter

def test_vision():
    pdf_path = "data/uploads/1_DSA patterns Cheat Sheet - Sheet1.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    print(f"--- Testing Vision on {pdf_path} ---")
    
    adapter = OllamaVisionAdapter()
    if not adapter.is_available():
        print("❌ Ollama not available!")
        return
        
    print(f"✅ Ollama connected ({adapter.model_name})")
    
    with pdfplumber.open(pdf_path) as pdf:
        # Test first 2 pages
        for i, page in enumerate(pdf.pages[:2]):
            print(f"\n--- Page {i+1} ---")
            im = page.to_image(resolution=300)
            
            # Convert to bytes
            img_byte_arr = io.BytesIO()
            im.original.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            print("Sending to Ollama...")
            desc = adapter.describe_image(img_bytes)
            
            print(f"RAW RESPONSE: {desc}")
            print(f"Calculated Length: {len(desc)}")
            
            if "Error" not in desc and len(desc) > 50:
                print("✅ Would be ACCEPTED by IngestionService")
            else:
                print("❌ Would be REJECTED by IngestionService")

if __name__ == "__main__":
    test_vision()

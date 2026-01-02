
import sys
import os
import io
import pdfplumber
import pytesseract
from PIL import Image
from app.infrastructure.vision.ollama_adapter import OllamaVisionAdapter

def test_recovery():
    pdf_path = "data/uploads/1_DSA patterns Cheat Sheet - Sheet1.pdf"
    print(f"--- Debugging Text Recovery for {pdf_path} ---")
    
    with pdfplumber.open(pdf_path) as pdf:
        # Focus on Page 1 where the issue likely is
        page = pdf.pages[0]
        im = page.to_image(resolution=300)
        original_image = im.original
        
        # 1. Test Tesseract PSM Modes
        modes = [3, 4, 6, 11, 12]
        print("\n=== Testing Tesseract Modes ===")
        for psm in modes:
            print(f"\n--- PSM {psm} ---")
            try:
                text = pytesseract.image_to_string(original_image, config=f'--psm {psm}')
                if "Happy" in text or "Cycle" in text:
                    print(f"✅ FOUND KEYWORDS! Length: {len(text)}")
                    print(f"Snippet: {text[:200].replace('\n', ' ')}...")
                else:
                    print(f"❌ Keywords not found. Length: {len(text)}")
                    print(f"First 100 chars: {text[:100].replace('\n', ' ')}")
            except Exception as e:
                print(f"Error: {e}")

        # 2. Test Vision AI Transcription
        print("\n=== Testing Vision AI Transcription ===")
        adapter = OllamaVisionAdapter()
        if adapter.is_available():
            # Convert to bytes
            img_byte_arr = io.BytesIO()
            original_image.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            prompts = [
                "Describe this image.",
                "Read all the text in this image exactly as written. Output only the text.",
                "Extract the text from the table columns. Start with 'Happy Number'."
            ]
            
            for p in prompts:
                print(f"\n--- Prompt: {p} ---")
                try:
                    # We need to hack the adapter to accept custom prompts or use a raw call if adapter doesn't support it
                    # The current adapter hardcodes the prompt. I will inspect the adapter code first, but for now assuming I can't change it easily without code edit.
                    # Actually, let's just run the standard one first to see if it changed.
                    # Wait, the adapter has a fixed prompt. I should probably use a direct request here for debugging.
                    pass 
                except Exception as e:
                    print(e)
            
            # Direct Ollama Call for Custom Prompts
            import requests
            import base64
            
            b64_img = base64.b64encode(img_bytes).decode('utf-8')
            
            for p in prompts:
                print(f"\n--- Custom Prompt: {p} ---")
                try:
                    payload = {
                        "model": "moondream",
                        "prompt": p,
                        "images": [b64_img],
                        "stream": False
                    }
                    resp = requests.post("http://localhost:11434/api/generate", json=payload)
                    if resp.status_code == 200:
                        res_text = resp.json().get('response', '')
                        if "Happy" in res_text or "Cycle" in res_text:
                            print(f"✅ FOUND KEYWORDS!")
                            print(f"Response: {res_text}")
                        else:
                            print(f"❌ Keywords not found.")
                            print(f"Response: {res_text[:200]}...")
                    else:
                        print(f"Error: {resp.status_code} - {resp.text}")
                except Exception as e:
                    print(f"Request Error: {e}")

if __name__ == "__main__":
    test_recovery()

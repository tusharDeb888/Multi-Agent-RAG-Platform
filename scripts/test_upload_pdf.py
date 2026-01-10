
import requests
import time
from reportlab.pdfgen import canvas

def create_pdf(filename):
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (500, 500), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((50, 250), "This is an image based PDF for PaddleOCR Test", fill=(0, 0, 0))
    img.save(filename, "PDF", resolution=100.0)
    print(f"Created image-based PDF {filename}")

def login():
    url = "http://localhost:8000/api/v1/auth/login"
    data = {
        "username": "admin",
        "password": "admin"
    }
    try:
        response = requests.post(url, data=data) 
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"Logged in as admin. Token: {token[:10]}...")
            return token
        else:
            print(f"Login Failed: {response.text}")
            return None
    except Exception as e:
        print(f"Login Exception: {e}")
        return None

def upload():
    token = login()
    if not token:
        return
        
    filename = "test_ocr.pdf"
    create_pdf(filename)
    
    url = "http://localhost:8000/api/v1/documents/upload"
    files = {'file': open(filename, 'rb')}
    
    headers = {'Authorization': f"Bearer {token}"}
        
    try:
        response = requests.post(url, files=files, headers=headers)
        print(f"Upload Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Upload Failed: {e}")

if __name__ == "__main__":
    # Assuming 'admin' user exists. 
    # I'll try to upload directly.
    upload()

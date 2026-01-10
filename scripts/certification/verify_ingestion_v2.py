import os
import time
import requests
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Configure check
API_URL = "http://localhost:8000/api/v1"
ADMIN_USERNAME = "admin"
ADMIN_PASS = "admin"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_token():
    resp = requests.post(f"{API_URL}/auth/login", data={"username": ADMIN_USERNAME, "password": ADMIN_PASS})
    resp.raise_for_status()
    return resp.json()["access_token"]

def create_dummy_pdf(filename, content="Test Content", pages=5):
    c = canvas.Canvas(filename, pagesize=letter)
    for i in range(pages):
        c.drawString(100, 750, f"Page {i+1} : {content}")
        c.drawString(100, 700, "This is a clean text PDF for Fast Path testing.")
        c.showPage()
    c.save()
    logger.info(f"Created {filename} with {pages} pages")

def verify_ingestion(filename, expect_partial=True):
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Upload
    logger.info(f"Uploading {filename}...")
    with open(filename, "rb") as f:
        files = {"file": (filename, f, "application/pdf")}
        start_time = time.time()
        resp = requests.post(f"{API_URL}/documents/upload", headers=headers, files=files, data={"department": "IT"})
        
    if resp.status_code != 202:
        logger.error(f"Upload failed: {resp.text}")
        return False
        
    doc_id = resp.json().get("id") or resp.json().get("document_id")
    if not doc_id:
        logger.error(f"Response missing ID: {resp.json()}")
        return False
        
    logger.info(f"Upload accepted. Doc ID: {doc_id}")
    
    # 2. Poll for Status
    status = "pending"
    partial_seen = False
    
    while status not in ["searchable", "failed", "completed"]:
        resp = requests.get(f"{API_URL}/documents/", headers=headers)
        docs = resp.json()
        target_doc = next((d for d in docs if d["id"] == doc_id), None)
        
        if not target_doc:
            logger.error("Document not found in list")
            return False
            
        new_status = target_doc["status"]
        if new_status != status:
            logger.info(f"Status changed: {status} -> {new_status} (Time: {time.time() - start_time:.2f}s)")
            status = new_status
            
        if status == "partial":
            partial_seen = True
            
        if status == "failed":
            logger.error(f"Ingestion FAILED: {target_doc.get('error_message')}")
            return False
            
        if time.time() - start_time > 60:
            logger.error("Timeout waiting for completion")
            return False
            
        time.sleep(0.5)
        
    logger.info(f"Ingestion Complete! Total Time: {time.time() - start_time:.2f}s")
    if expect_partial and not partial_seen:
        logger.warning("Did NOT see PARTIAL status (Might be too fast?)")
    elif expect_partial and partial_seen:
        logger.info("Confirmed PARTIAL status transition ✅")
        
    return True

if __name__ == "__main__":
    # Test 1: Clean PDF (FAST PATH)
    create_dummy_pdf("test_fast_v2.pdf", "Fast Path Ingestion Test", pages=20)
    if verify_ingestion("test_fast_v2.pdf"):
        logger.info("✅ FAST PATH Test Passed")
    else:
        logger.error("❌ FAST PATH Test Failed")
        
    # Clean up
    if os.path.exists("test_fast_v2.pdf"):
        os.remove("test_fast_v2.pdf")

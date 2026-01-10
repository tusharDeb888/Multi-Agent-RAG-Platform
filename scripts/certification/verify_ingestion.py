import sys
import os
import requests
import json
import time
from loguru import logger

# Configuration
API_URL = "http://localhost:8000/api/v1"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"

def get_token(username, password):
    try:
        resp = requests.post(f"{API_URL}/auth/login", data={"username": username, "password": password})
        if resp.status_code == 200:
            return resp.json()["access_token"]
        return None
    except:
        return None

def create_large_dummy_file(filename, size_mb=1):
    """Create a dummy file with repetitive content to simulate size."""
    with open(filename, "w") as f:
        # 1MB = 1024*1024 bytes.
        chunk = "This is a dummy sentence for ingestion testing. " * 20 # ~1KB
        for _ in range(int(size_mb * 1024)):
            f.write(chunk)
    return filename

def verify_ingestion():
    logger.info("📄 Starting Document Ingestion Verification...")
    
    token = get_token(ADMIN_USER, ADMIN_PASS)
    if not token:
        logger.error("Auth failed")
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Create Test File (5MB)
    filename = "test_ingestion_large.txt"
    create_large_dummy_file(filename, size_mb=5)
    logger.info(f"Created {filename} (5MB)")
    
    # 2. Upload
    try:
        files = {'file': (filename, open(filename, 'rb'), 'text/plain')}
        data = {'title': "Ingestion Test Doc", 'departments': json.dumps(["General"])}
        
        start_time = time.time()
        resp = requests.post(f"{API_URL}/documents/upload", headers=headers, files=files, data=data)
        
        if resp.status_code != 202:
             logger.error(f"❌ Upload failed: {resp.status_code} {resp.text}")
             return
             
        doc_id = resp.json()['id']
        logger.info(f"✅ Upload accepted. Doc ID: {doc_id}")
        
        # 3. Poll Status
        max_retries = 30
        for i in range(max_retries):
            resp = requests.get(f"{API_URL}/documents/{doc_id}", headers=headers)
            status = resp.json()['status']
            logger.info(f"Poll {i+1}: Status = {status}")
            
            if status == "searchable":
                elapsed = time.time() - start_time
                logger.info(f"✅ Ingestion Complete in {elapsed:.2f}s")
                break
            elif status == "failed":
                logger.error(f"❌ Ingestion Failed: {resp.json().get('error_message')}")
                break
                
            time.sleep(1)
        else:
            logger.error("❌ Ingestion timed out")
            
    finally:
        if os.path.exists(filename):
            os.remove(filename)
        # Cleanup DB
        if 'doc_id' in locals():
            requests.delete(f"{API_URL}/documents/{doc_id}", headers=headers)
            logger.info(f"🧹 Deleted test doc {doc_id}")

    logger.info("📄 Ingestion Verification Complete.")

if __name__ == "__main__":
    verify_ingestion()

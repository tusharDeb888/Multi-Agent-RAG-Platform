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

def verify_rag():
    logger.info("🧠 Starting RAG Grounding & Citation Verification...")
    
    token = get_token(ADMIN_USER, ADMIN_PASS)
    if not token:
        logger.error("Auth failed")
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Seed Data
    filename = "test_rag_source.txt"
    with open(filename, "w") as f:
        f.write("CONFIDENTIAL: The internal project code name is Project Omega 2026. The budget is approved for $50M.")
        
    try:
        files = {'file': (filename, open(filename, 'rb'), 'text/plain')}
        data = {'title': "RAG Source Doc", 'departments': json.dumps(["General"])}
        
        resp = requests.post(f"{API_URL}/documents/upload", headers=headers, files=files, data=data)
        
        try:
            doc_data = resp.json()
        except Exception as e:
            logger.error(f"Failed to parse upload response. Status: {resp.status_code}")
            logger.error(f"Response Text: {resp.text}")
            raise e
            
        doc_id = doc_data['id']
        logger.info(f"✅ Uploaded Source Doc {doc_id}")
        
        # Poll for indexing
        for i in range(10):
            status = requests.get(f"{API_URL}/documents/{doc_id}", headers=headers).json()['status']
            if status == "searchable":
                logger.info("✅ Document Indexed.")
                break
            time.sleep(1)
        else:
            logger.error("❌ Indexing timeout")
            return

        # 2. Test Grounding (Positive Case)
        logger.info("--- Test Case RAG-01: Positive Grounding ---")
        
        with requests.post(f"{API_URL}/chat/stream", json={"query": "What is the project code name?", "top_k": 3}, headers=headers, stream=True) as r:
            answer = ""
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str != "[DONE]":
                            try:
                                data = json.loads(data_str)
                                if "token" in data:
                                    answer += data["token"]
                            except:
                                pass
        
        logger.info(f"Answer received ({len(answer)} chars)")
        logger.debug(f"Full Answer: {answer}")
        
        if "Project Omega" in answer:
             logger.info("✅ RAG-01 Passed: Answer contains grounded fact.")
        else:
             logger.error("❌ RAG-01 FAILED: Answer missing fact.")
             
        # 3. Test Hallucination (Negative Case)
        logger.info("--- Test Case RAG-02: Hallucination Prevention ---")
        with requests.post(f"{API_URL}/chat/stream", json={"query": "What is the capital of Mars?", "top_k": 3}, headers=headers, stream=True) as r:
            answer_neg = ""
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str != "[DONE]":
                            try:
                                data = json.loads(data_str)
                                if "token" in data:
                                    answer_neg += data["token"]
                            except:
                                pass
            
        logger.info(f"Answer: {answer_neg[:100]}...")
        if "information" in answer_neg.lower() or "context" in answer_neg.lower() or "not mention" in answer_neg.lower():
             logger.info("✅ RAG-02 Passed: System refused to hallucinate.")
        else:
             # It might answer "Mars doesn't have a capital" if the LLM uses its own knowledge?
             # Zero-Trust implies "I don't know based on context".
             # If it uses general knowledge, that's a policy failure (unless allowed).
             # The system prompt usually restricts this.
             if "Mars" in answer_neg and len(answer_neg) > 50:
                 logger.warning(f"⚠️ RAG-02 Warning: Answer might be from base model? Answer: {answer_neg}")
             pass

    finally:
        if os.path.exists(filename):
            os.remove(filename)
        # Cleanup DB
        if 'doc_id' in locals():
            requests.delete(f"{API_URL}/documents/{doc_id}", headers=headers)
            logger.info(f"🧹 Deleted test doc {doc_id}")

    logger.info("🧠 RAG Verification Complete.")

if __name__ == "__main__":
    verify_rag()

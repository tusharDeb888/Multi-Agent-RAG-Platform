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
TEST_USER_HR = "testuser1" # HR
TEST_USER_HR_PASS = "testuser1"
TEST_USER_IT = "testuser2" # IT
TEST_USER_IT_PASS = "testuser2"

# Files to clean up
CREATED_DOC_IDS = []



def get_token_with_retry(username, password):
    for i in range(3):
        resp = requests.post(f"{API_URL}/auth/login", data={"username": username, "password": password})
        if resp.status_code == 200:
            return resp.json()["access_token"]
        elif "Rate limit" in resp.text:
            logger.warning(f"Rate limit hit for {username}. Waiting 60s...")
            time.sleep(60)
            continue
        else:
            logger.error(f"Login failed for {username}: {resp.text}")
            return None
    return None

def create_dummy_file(filename, content="Dummy content"):
    with open(filename, "w") as f:
        f.write(content)
    return filename

def upload_doc(token, filename, departments, title, content="Dummy content"):
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create simple text file
    create_dummy_file(filename, content)
    
    files = {'file': (filename, open(filename, 'rb'), 'text/plain')}
    data = {'title': title, 'departments': json.dumps(departments)}
    
    resp = requests.post(f"{API_URL}/documents/upload", headers=headers, files=files, data=data)
    if resp.status_code == 202:
        doc_data = resp.json()
        doc_id = doc_data['id']
        logger.info(f"✅ Uploaded {filename} (ID: {doc_id}) with tags {departments}")
        CREATED_DOC_IDS.append(doc_id)
        os.remove(filename)
        return doc_id
    elif resp.status_code == 200 and resp.json().get('duplicate'):
         doc_id = resp.json()['id']
         logger.info(f"ℹ️ Document {filename} (ID: {doc_id}) already exists.")
         # Don't add to cleanup list if we didn't create it, or maybe we do? 
         # Let's add it to verify, but maybe not delete if it was pre-existing.
         # For this test, we assume we own it.
         CREATED_DOC_IDS.append(doc_id)
         os.remove(filename)
         return doc_id
    else:
        logger.error(f"❌ Upload failed: {resp.status_code} {resp.text}")
        os.remove(filename)
        return None

def check_visibility(token, user_label, expected_ids, forbidden_ids):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{API_URL}/documents/", headers=headers, params={"limit": 100})
    if resp.status_code != 200:
        logger.error(f"❌ Failed to list docs for {user_label}: {resp.status_code}")
        return False
        
    docs = resp.json()
    visible_ids = [d['id'] for d in docs]
    
    success = True
    # Check Expected
    for eid in expected_ids:
        if eid not in visible_ids:
            logger.error(f"❌ {user_label} SHOULD see Doc {eid} but didn't.")
            success = False
        else:
            logger.info(f"✅ {user_label} correctly sees Doc {eid}")
            
    # Check Forbidden
    for fid in forbidden_ids:
        if fid in visible_ids:
            logger.error(f"❌ {user_label} SAW FORBIDDEN Doc {fid}!")
            success = False
        else:
            logger.info(f"✅ {user_label} correctly BLOCKED from Doc {fid}")
            
    return success

def verify_direct_access(token, user_label, doc_id, should_succeed):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{API_URL}/documents/{doc_id}", headers=headers)
    
    if should_succeed:
        if resp.status_code == 200:
            logger.info(f"✅ {user_label} can access Doc {doc_id} directly.")
            return True
        else:
            logger.error(f"❌ {user_label} failed to access Doc {doc_id} directly. Code: {resp.status_code}")
            return False
    else:
        if resp.status_code == 403:
            logger.info(f"✅ {user_label} correctly denied access to Doc {doc_id} directly.")
            return True
        else:
            logger.error(f"❌ {user_label} WAS NOT DENIED access to Doc {doc_id}. Code: {resp.status_code}")
            return False

def cleanup(token):
    headers = {"Authorization": f"Bearer {token}"}
    for doc_id in set(CREATED_DOC_IDS):
        logger.info(f"🧹 Deleting Doc {doc_id}...")
        requests.delete(f"{API_URL}/documents/{doc_id}", headers=headers)

def verify_rbac():
    logger.info("🔐 Starting End-to-End RBAC Verification...")
    
    # 0. Authenticate
    admin_token = get_token_with_retry(ADMIN_USER, ADMIN_PASS)
    hr_token = get_token_with_retry(TEST_USER_HR, TEST_USER_HR_PASS)
    it_token = get_token_with_retry(TEST_USER_IT, TEST_USER_IT_PASS)
    
    if not (admin_token and hr_token and it_token):
        logger.error("Authentication failed. Aborting.")
        return

    # 1. Seed Data
    logger.info("--- Data Seeding ---")
    
    # IT Document
    it_doc_id = upload_doc(admin_token, "test_it_policy.txt", ["IT"], "IT Policy - Confidential", "Unique IT Content 123")
    
    # HR Document
    hr_doc_id = upload_doc(admin_token, "test_hr_handbook.txt", ["HR"], "HR Handbook", "Unique HR Content 456")
    
    # General Document
    gen_doc_id = upload_doc(admin_token, "test_general_notice.txt", ["General"], "General Notice", "Unique General Content 789")
    
    if not (it_doc_id and hr_doc_id and gen_doc_id):
        logger.error("Failed to seed data. Aborting.")
        cleanup(admin_token)
        return
        
    # Wait for async triggers (although we are testing API list which relies on DB, so should be instant)
    time.sleep(1) 
    
    # 2. Run Tests
    all_passed = True
    
    # Case A: SEC-01 IT User
    # Should see IT and General. Should NOT see HR.
    logger.info("\n--- Test A: IT User View ---")
    if not check_visibility(it_token, "IT User", [it_doc_id, gen_doc_id], [hr_doc_id]):
        all_passed = False
        
    # Case B: SEC-01 HR User
    # Should see HR and General. Should NOT see IT.
    logger.info("\n--- Test B: HR User View ---")
    if not check_visibility(hr_token, "HR User", [hr_doc_id, gen_doc_id], [it_doc_id]):
        all_passed = False
        
    # Case C: SEC-03 Direct Access Check
    # HR tries to GET IT Doc
    logger.info("\n--- Test C: Direct Access Enforcement ---")
    if not verify_direct_access(hr_token, "HR User", it_doc_id, should_succeed=False):
        all_passed = False
        
    # General should be accessible
    if not verify_direct_access(hr_token, "HR User", gen_doc_id, should_succeed=True):
        all_passed = False

    # 3. Cleanup
    logger.info("\n--- Cleanup ---")
    cleanup(admin_token)
    
    if all_passed:
        logger.info("\n🎉 RBAC CERTIFICATION PASSED: All checks green.")
    else:
        logger.error("\n❌ RBAC CERTIFICATION FAILED: See logs above.")

if __name__ == "__main__":
    verify_rbac()

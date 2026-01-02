import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"

def test_delete(doc_id):
    # 1. Login
    print("Logging in...")
    resp = requests.post(f"{BASE_URL}/auth/login", data={
        "username": "admin",
        "password": "admin"
    })
    
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        sys.exit(1)
        
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Try Delete
    print(f"Attempting to delete document {doc_id}...")
    del_resp = requests.delete(f"{BASE_URL}/documents/{doc_id}", headers=headers)
    
    if del_resp.status_code == 204:
        print("Success: Document deleted (204).")
    else:
        print(f"Failed: {del_resp.status_code} - {del_resp.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_delete_api.py <doc_id>")
    else:
        test_delete(sys.argv[1])

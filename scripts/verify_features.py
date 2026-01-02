import requests
import json
import os

BASE_URL = "http://localhost:8000/api/v1"

def get_token():
    try:
        data = {
            "username": "admin",
            "password": "admin"
        }
        response = requests.post(f"{BASE_URL}/auth/login", data=data) 
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        print(f"Login failed: {e}")
        return None

def test_chitchat(token):
    print("\n--- Testing Chitchat Filtering ---")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Simple query
    query = "Hi there"
    try:
        response = requests.post(f"{BASE_URL}/chat/query", json={"query": query}, headers=headers)
        if response.status_code == 200:
            data = response.json()
            citations = data.get("citations", [])
            print(f"Query: '{query}'")
            print(f"Citations count: {len(citations)}")
            print(f"Answer: {data.get('answer')[:100]}...")
            
            if len(citations) == 0:
                print("✅ Smart filtering working (0 citations)")
            else:
                print("❌ Smart filtering failed (Citations present)")
        else:
            print(f"Chat request failed: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def test_upload_txt(token):
    print("\n--- Testing TXT Upload ---")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create dummy txt
    filename = "dummy_test.txt"
    with open(filename, "w") as f:
        f.write("This is a test document content for ingestion verification.")
        
    try:
        with open(filename, "rb") as f:
            files = {"file": f}
            response = requests.post(
                f"{BASE_URL}/documents/upload", 
                headers=headers, 
                files=files, 
                data={"department": "IT"}
            )
            
        if response.status_code == 202:
            print(f"✅ TXT Upload successful: {response.json()['message']}")
        else:
            print(f"❌ TXT Upload failed: {response.status_code} {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    token = get_token()
    if token:
        test_chitchat(token)
        test_upload_txt(token)

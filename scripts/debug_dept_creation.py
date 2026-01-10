import requests
import os
import sys
import json

BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = os.getenv("TEST_PASSWORD", "admin")

def debug_dept():
    # 1. Login
    print(f"Logging in as {USERNAME}...")
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", data={"username": USERNAME, "password": PASSWORD})
        if resp.status_code != 200:
            print(f"Login failed: {resp.text}")
            return
        token = resp.json()["access_token"]
        print("Login success.")
    except Exception as e:
        print(f"Login error: {e}")
        return

    # 2. Check Role (via inspection or assumption)
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Create Department
    dept_name = "Debug Dept " + os.urandom(2).hex()
    payload = {
        "name": dept_name,
        "description": "Debug Description"
    }
    
    print(f"Creating department: {dept_name}")
    try:
        resp = requests.post(f"{BASE_URL}/departments/", json=payload, headers=headers)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code == 201:
            print("✅ Department created successfully.")
        else:
            print("❌ Failed.")
            
    except Exception as e:
        print(f"Request error: {e}")

if __name__ == "__main__":
    debug_dept()

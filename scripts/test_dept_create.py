import requests
import json

API_URL = "http://localhost:8000/api/v1"

# Login as admin
resp = requests.post(f"{API_URL}/auth/login", data={"username": "admin", "password": "admin"})
if resp.status_code != 200:
    print(f"Login failed: {resp.status_code}")
    print(resp.text)
    exit(1)

token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Try to create a department
dept_data = {
    "name": "Test Department",
    "description": "Test description"
}

print("Creating department...")
resp = requests.post(f"{API_URL}/departments/", json=dept_data, headers=headers)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

if resp.status_code != 201:
    print("\n❌ FAILED")
else:
    print("\n✅ SUCCESS")

import requests
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"

def test_cors():
    print("\n--- Testing CORS ---")
    
    # Test Trusted Origin
    headers = {"Origin": "http://localhost:5173"}
    try:
        response = requests.options(f"{BASE_URL}/auth/login", headers=headers)
        if (response.status_code == 200 or response.status_code == 405) and response.headers.get("access-control-allow-origin") == "http://localhost:5173":
             print("✅ Trusted origin allowed")
        else:
             print(f"❌ Trusted origin failed: {response.status_code}")
             print(response.headers)
    except Exception as e:
        print(f"❌ Error testing trusted origin: {e}")

    # Test Untrusted Origin
    headers = {"Origin": "http://evil.com"}
    try:
        response = requests.options(f"{BASE_URL}/auth/login", headers=headers)
        if "access-control-allow-origin" not in response.headers:
             print("✅ Untrusted origin blocked (no allow header)")
        else:
             print(f"❌ Untrusted origin allowed: {response.headers.get('access-control-allow-origin')}")
    except Exception as e:
        print(f"❌ Error testing untrusted origin: {e}")

def test_rate_limit():
    print("\n--- Testing Rate Limiting (Login: 5/min) ---")
    url = f"{BASE_URL}/auth/login"
    
    # We expect the 6th request to fail within a minute
    for i in range(1, 8):
        try:
            # Send invalid login to just trigger the endpoint
            data = {"username": "test", "password": "wrongpassword"}
            response = requests.post(url, data=data)
            
            if response.status_code == 429:
                print(f"✅ Request {i}: 429 Too Many Requests (Rate limit working)")
                return
            elif response.status_code == 401:
                print(f"ℹ️ Request {i}: 401 Unauthorized (Allowed)")
            else:
                print(f"⚠️ Request {i}: {response.status_code} (Unexpected)")
                
        except Exception as e:
            print(f"❌ Request {i} error: {e}")
            
    print("❌ Rate limit did not trigger after 7 requests")

if __name__ == "__main__":
    test_cors()
    test_rate_limit()

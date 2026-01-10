import requests
import sys

API_URL = "http://localhost:8000/api/v1"

def verify_auth_guard():
    print("Testing Auth Guards...")
    
    # 1. Unauthenticated Access (No Token)
    print("1. Testing No Token (Expect 401)...")
    resp = requests.get(f"{API_URL}/chat/history")
    if resp.status_code == 401:
        print("   ✅ Passed: Got 401 Unauthorized")
    else:
        print(f"   ❌ Failed: Got {resp.status_code}")
        return False

    # 2. Invalid Token
    print("2. Testing Invalid Token (Expect 401)...")
    headers = {"Authorization": "Bearer invalid_token_123"}
    resp = requests.get(f"{API_URL}/chat/history", headers=headers)
    if resp.status_code == 401:
        print("   ✅ Passed: Got 401 Unauthorized")
    else:
        print(f"   ❌ Failed: Got {resp.status_code}")
        return False
        
    print("\nAuth Guards Verified Successfully.")
    return True

if __name__ == "__main__":
    try:
        if verify_auth_guard():
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

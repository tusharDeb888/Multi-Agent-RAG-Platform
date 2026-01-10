import requests
import sys
import time
import os

API_URL = "http://localhost:8000/api/v1"
# Use /openapi.json as a public endpoint that likely isn't decorated manually
TARGET_URL = "http://localhost:8000/api/v1/openapi.json"

def verify_rate_limit():
    print(f"Testing Rate Limits on {TARGET_URL}...")
    limit = 110
    start = time.time()
    
    hit_count = 0
    got_429 = False
    
    for i in range(limit):
        try:
            resp = requests.get(TARGET_URL)
            if resp.status_code == 429:
                print(f"✅ Hit Rate Limit (429) at request #{i+1}")
                got_429 = True
                break
            hit_count += 1
            if i % 20 == 0:
                print(f"   Request {i+1}: {resp.status_code}")
        except Exception as e:
            print(f"Connection error: {e}")
            break
            
    print(f"Total Hits: {hit_count}")
    if got_429:
        print("PASS: Global Rate Limiting is active.")
        return True
    else:
        print("FAIL: Did not hit 429 after 110 requests.")
        return False

if __name__ == "__main__":
    if verify_rate_limit():
        sys.exit(0)
    else:
        sys.exit(1)

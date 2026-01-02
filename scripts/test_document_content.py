
import requests
import sys

def test_content_endpoint():
    # Login to get token
    login_url = "http://localhost:8000/api/v1/auth/login"
    # Using default/test creds if you know them, otherwise might fail if auth required
    # But for now assuming I can test if I have a valid token or just check 401 response which means endpoint exists
    
    # Actually, let's just check if endpoint 404s or 401s (which means it matches)
    # vs 404 Not Found (route not found)
    
    doc_id = 936 # random ID from logs
    
    # Case 1: No Token
    url_no_token = f"http://127.0.0.1:8000/api/v1/documents/{doc_id}/content"
    print(f"\nTesting No Token: {url_no_token}")
    resp1 = requests.get(url_no_token, timeout=5)
    print(f"Status: {resp1.status_code}, Detail: {resp1.json().get('detail')}")
    
    # Case 2: Query Token (Invalid)
    url_query_token = f"http://127.0.0.1:8000/api/v1/documents/{doc_id}/content?token=rubbish"
    print(f"\nTesting Query Token: {url_query_token}")
    resp2 = requests.get(url_query_token, timeout=5)
    print(f"Status: {resp2.status_code}, Detail: {resp2.json().get('detail')}")
    
    if resp1.status_code == 401 and resp1.json().get('detail') == "Not authenticated":
        print("PASS: Missing token correctly identified")
    else:
        print("FAIL: Missing token check failed")
        
    if resp2.status_code == 401 and resp2.json().get('detail') == "Could not validate credentials":
        print("PASS: Query token picked up and validated (failed as expected)")
    else:
        print("FAIL: Query token check failed")

if __name__ == "__main__":
    test_content_endpoint()

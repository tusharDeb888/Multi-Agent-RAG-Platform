import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin_password"  # Assuming this from seed_db, will check

def get_token():
    url = f"{BASE_URL}/auth/login"
    try:
        # Try form data first as OAuth2PasswordRequestForm usually expects form data
        data = {
            "username": USERNAME,
            "password": "admin" 
        }
        print(f"Logging in as {USERNAME}...")
        response = requests.post(url, data=data)
        
        if response.status_code != 200:
            print(f"Login failed: {response.status_code} {response.text}")
            return None
            
        return response.json()["access_token"]
    except Exception as e:
        print(f"Login error: {e}")
        return None

def test_history(token):
    url = f"{BASE_URL}/chat/history"
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Requesting history from {url}...")
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            print("Success!")
            print(f"Items: {len(response.json())}")
            print(response.json())
        else:
            print(f"Failed: {response.status_code} {response.text}")
            
    except Exception as e:
        print(f"Request error: {e}")

if __name__ == "__main__":
    # Check if requests is installed, if not, use urllib
    try:
        import requests
        
        # Need to know the correct password. 
        # Checking seed_db.py content might be needed if this fails.
        token = get_token()
        if token:
            test_history(token)
            
    except ImportError:
        print("requests module not found. Use pip install requests or try urllib.")

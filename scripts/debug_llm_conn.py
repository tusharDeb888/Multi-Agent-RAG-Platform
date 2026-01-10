import requests
import json

base_url = "http://localhost:11434"
model = "llama3.2:3b"

print(f"Testing connection to Ollama at {base_url} with model {model}...")

url = f"{base_url}/api/chat"
payload = {
    "model": model,
    "messages": [
        {"role": "user", "content": "Hello, are you working?"}
    ],
    "stream": False
}

try:
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        print("✅ Success!")
        print("Response:", res.json()['message']['content'])
    else:
        print(f"❌ Failed with status {res.status_code}")
        print("Error:", res.text)
except Exception as e:
    print(f"❌ Connection Failed: {e}")

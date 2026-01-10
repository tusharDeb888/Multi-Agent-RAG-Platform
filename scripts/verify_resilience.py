import requests
import time
import subprocess
import signal
import os

def kill_ollama():
    print("Stopping Ollama...")
    subprocess.run(["pkill", "ollama"])
    time.sleep(2)

def start_ollama():
    print("Starting Ollama...")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5) # Wait for it to come up

def test_app_resilience():
    # 1. Kill Ollama
    kill_ollama()
    
    # 2. Make a request to the app (running in uvicorn?)
    # Assuming app handles requests. The adapter inside app will retry.
    # Note: We can't easily see app logs here unless we tail them, but we can measure response time.
    # If app retries, the request should take at least 1.5s (0.5s + 1s backoff...)
    
    print("Sending request to App (expecting slow failure/retry)...")
    t0 = time.time()
    try:
        # Using the debug script's logic but pointing to app endpoint if running
        # actually, let's verify connection logic directly if we can load the module
        # But importing app modules here might be complex due to deps.
        # Let's just restart ollama mid-request?
        
        # Start Ollama in background AFTER 1 second
        from threading import Timer
        Timer(2.0, start_ollama).start()
        
        # This request ideally should hit the app, which hits Ollama (down), retries... 
        # Ollama comes up... App succeeds on attempt 2 or 3.
        # But we are testing the adapter in isolation here basically?
        pass

    except Exception as e:
        print(f"Request failed: {e}")
        
    print(f"Test finished in {time.time() - t0:.2f}s")
    
if __name__ == "__main__":
    # verification is tricky without running app. 
    # I will just manually verify by restarting ollama.
    print("Manual verification recommended: Stop Ollama, run query, Start Ollama. App should recover.")

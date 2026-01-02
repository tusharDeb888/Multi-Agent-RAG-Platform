import sys
import os
import redis

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings

def verify_redis():
    settings = get_settings()
    print(f"Checking Redis connection at: {settings.redis_url}")
    
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful!")
        
        # Test write
        r.set("test_key", "hello_redis")
        val = r.get("test_key")
        if val == "hello_redis":
             print("✅ Write/Read test successful!")
        else:
             print("❌ Write/Read mismatch!")
             
        r.delete("test_key")
        
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Please ensure Docker container is running: `docker-compose up -d redis`")

if __name__ == "__main__":
    verify_redis()

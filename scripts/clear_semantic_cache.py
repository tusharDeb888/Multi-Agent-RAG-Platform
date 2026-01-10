import sys
import os
import asyncio
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.application.services.semantic_cache_service import SemanticCacheService

async def clear_cache():
    print("Initializing Semantic Cache Service...")
    svc = SemanticCacheService()
    
    print(f"Dropping collection '{svc.collection_name}'...")
    try:
        svc.client.drop_collection(svc.collection_name)
        print("✅ Collection dropped.")
        
        print("Re-creating empty collection...")
        svc._ensure_collection()
        print("✅ Cache cleared and ready.")
        
    except Exception as e:
        print(f"❌ Failed to clear cache: {e}")

if __name__ == "__main__":
    asyncio.run(clear_cache())

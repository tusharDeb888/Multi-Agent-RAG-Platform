import sys
import os
import asyncio
import numpy as np
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.core.config import get_settings

async def verify_milvus_fix():
    print("Initializing Milvus Store...")
    store = MilvusVectorStore()
    
    # Fake query vector (dim=384 for all-MiniLM-L6-v2)
    dim = 384
    query_vec = np.random.rand(dim).astype(np.float32)
    
    # Fake IDs to search for (assumes some chunks exist, or we catch empty result)
    # We will just test the method execution, not the result content
    allowed_ids = [1, 2, 3, 4, 5]
    
    print(f"Testing search_exact_subset with {len(allowed_ids)} IDs...")
    try:
        results = await store.search_exact_subset(query_vec, allowed_ids, top_k=5)
        print("✅ search_exact_subset executed successfully!")
        print(f"Results returned: {len(results)}")
    except AttributeError:
        print("❌ FAILED: Attribute 'search_exact_subset' missing!")
    except Exception as e:
        print(f"❌ FAILED with error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_milvus_fix())

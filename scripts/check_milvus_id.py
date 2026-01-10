
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.vector_store.milvus_store import MilvusVectorStore

def check_id():
    store = MilvusVectorStore()
    
    # Try to fetch the chunk ID found in inspect script
    chunk_id = 21479 
    
    print(f"Checking Milvus for Chunk ID {chunk_id}...")
    try:
        res = store.client.get(store.collection_name, ids=[chunk_id])
        if res:
            print(f"✅ Found Chunk {chunk_id} in Milvus!")
            print(f"Data: {res}")
        else:
            print(f"❌ Chunk {chunk_id} NOT FOUND in Milvus.")
            
        # Also check count
        count_res = store.client.query(store.collection_name, filter="", output_fields=["count(*)"])
        print(f"Total count (approx): {count_res}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_id()

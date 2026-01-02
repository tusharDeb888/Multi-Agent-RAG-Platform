"""
Test Oracle Vector Search.
"""
from app.infrastructure.vector_store.oracle_store import OracleVectorStore
from app.domain.models import DocumentChunk
from app.core.database import SessionLocal
import numpy as np
import time

def test_oracle_vector():
    print("Testing Oracle Vector Store...")
    
    # 1. Initialize
    try:
        store = OracleVectorStore()
    except Exception as e:
        print(f"Failed to init store: {e}")
        return
    
    # 2. Mock Data (Need existing chunk ID in table)
    db = SessionLocal()
    chunk = db.query(DocumentChunk).first()
    
    if not chunk:
        print("⚠️ No chunks in DB to test with. Run ingestion first or manual insert.")
        return

    print(f"Using Chunk ID: {chunk.id}")
    
    # 3. Add Vector
    # Dimension 384
    vec = np.random.rand(384).tolist()
    
    try:
        store.add_vectors([vec], [chunk.id])
        print("✅ Vector added/updated.")
    except Exception as e:
        print(f"❌ Failed to add vector: {e}")
        return
    
    # 4. Search
    print("Searching...")
    try:
        results = store.search(vec, top_k=5)
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return
    
    print(f"Results: {results}")
    
    # Verify we found ourselves (score close to 1.0)
    found = False
    for cid, score in results:
        if cid == chunk.id:
            print(f"✅ Found chunk {cid} with score {score:.4f}")
            found = True
            break
            
    if not found:
        print("❌ Chunk not found in results!")

if __name__ == "__main__":
    test_oracle_vector()

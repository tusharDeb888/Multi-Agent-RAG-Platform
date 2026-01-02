
import asyncio
import sys
import os

# Set up environment
os.environ["VISION_PROVIDER"] = "ollama" # Mock config if needed
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from app.domain.models import User

async def debug_query():
    print("Initializing RAG Service...")
    db = SessionLocal()
    rag = RAGService(db=db)
    
    query = "Explain the Sliding Window pattern"
    user_id = 1 # Assumption: User ID 1 exists
    
    print(f"\nRunning Query: '{query}'")
    
    # 1. Inspect Vector/BM25 retrieval first
    # We call internal method if possible or just use public query but add logging
    # Let's inspect _retrieve_context directly by accessing internal methods
    
    # Needs async run
    try:
        print("--- Step 1: Retrieval (Vector + BM25) ---")
        retrieval_result = await rag._retrieve_context(user_id=user_id, query=query, top_k=5)
        
        final_chunks = retrieval_result["final_chunks"]
        candidate_count = retrieval_result["candidate_count"]
        
        print(f"\nCandidates found: {candidate_count}")
        print(f"Final chunks after Reranking: {len(final_chunks)}")
        
        if not final_chunks:
            print("No chunks passed the reranker!")
        
        print("\n--- Final Selected Chunks ---")
        for i, chunk in enumerate(final_chunks):
            print(f"\n[{i+1}] Doc: {chunk.document.filename} (Page {chunk.page_number})")
            print(f"    Chunk ID: {chunk.id}")
            print(f"    Content Preview: {chunk.content[:150]}...")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(debug_query())

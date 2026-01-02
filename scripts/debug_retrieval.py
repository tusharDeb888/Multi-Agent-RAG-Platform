"""
Debug Retrieval Pipeline.
Traces Vector, BM25, and Reranker scores for a specific query.
"""
import asyncio
import logging
import sys
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService

# Configure Logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger("app.application.services.rag_service")
logger.setLevel(logging.DEBUG)

async def debug_query(query: str, user_id: int = 1):
    print(f"\n--- Debugging Query: '{query}' ---\n")
    
    db = SessionLocal()
    try:
        rag = RAGService(db)
        
        # 0. Check Retrieval Stats
        print("[0] In-Memory Stats:")
        if rag.bm25.is_fitted:
            print(f"  BM25 Check: Fitted.")
        else:
            print("  BM25 Check: NOT FITTED!")
            
        # 1. Run Retrieval Step Directly
        t0 = asyncio.get_event_loop().time()
        
        # We need to call internal method _retrieve_context directly to see intermediates?
        # Or we can just run query() and rely on the DEBUG logs I enabled.
        # But _retrieve_context returns the chunks, which is better.
        
        print("\n[1] Running Retrieval...")
        retrieval_res = await rag._retrieve_context(user_id=user_id, query=query, top_k=5)
        
        final_chunks = retrieval_res["final_chunks"]
        candidate_count = retrieval_res["candidate_count"]
        
        print(f"\n[2] Retrieval Results:")
        print(f"  Total Candidates (Vector + BM25): {candidate_count}")
        print(f"  Final Selected Chunks (After Rerank): {len(final_chunks)}")
        
        print("\n[3] Content Preview:")
        for i, chunk in enumerate(final_chunks):
            doc_name = chunk.document.filename if chunk.document else "Unknown"
            print(f"  Chunk {i+1} [Doc: {doc_name} | ID: {chunk.id}]:")
            print(f"    Preview: {chunk.content[:200]}...")
            print("    ---")
            
        if not final_chunks:
            print("\n❌ FAILURE: No chunks selected for context!")
            
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        q = "find a DSA pattern of Happy Number"
    else:
        q = sys.argv[1]
        
    asyncio.run(debug_query(q))

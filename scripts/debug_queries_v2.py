#!/usr/bin/env python3
"""
Debug Script V2: Validates Query Expansion and Strict Retrieval.
Tests if "tell me about Charlie" triggers entity extraction and passes retrieval.
"""
import sys
import os
import asyncio
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from loguru import logger

# Configure logger to show DEBUG
logger.remove()
logger.add(sys.stderr, level="INFO") # Change to DEBUG to see reranker scores

async def test_retrieval(query: str):
    print(f"\n{'='*60}")
    print(f"Testing Query: {query}")
    print(f"{'='*60}")
    
    db = SessionLocal()
    try:
        rag = RAGService(db=db)
        
        # 1. Test Expansion Logic
        print("\n--- Phase 1: Expansion ---")
        expanded = await rag._expand_query(query)
        print(f"Original: '{query}'")
        print(f"Expanded: '{expanded}'")
        
        if len(expanded) > len(query) and query not in expanded and "Charlie" in query:
             print("⚠️ Expansion replaced original text completely. Checking if entities preserved...")
             if "Charlie" not in expanded:
                 print("❌ CRITICAL: Entity 'Charlie' lost in expansion!")
             else:
                 print("✓ Entity preserved.")

        # 2. Test Retrieval & Reranking (End-to-End)
        print("\n--- Phase 2: Retrieval & Reranking ---")
        # We use a restricted user (ID 2 usually, or 1 for admin)
        # Let's use Admin (ID 1) to ensure we see all docs first
        result = await rag.query(user_id=1, query=query)
        
        candidates = result.get('chunks_retrieved', 0)
        final = result.get('chunks_after_filtering', 0) # This maps to accessible_count in code, but let's check chunks
        
        # Note: 'chunks_after_filtering' in query return is actually accessible_count
        # We need to see how many made it to context.
        # Check citations to see what was actually used.
        citations = result.get('citations', [])
        
        print(f"Candidates found: {candidates}")
        print(f"Final chunks used: {len(citations)} (implied from citations)")
        
        if len(citations) > 0:
            print(f"✓ Retrieval Success! Used {len(citations)} chunks.")
            for cit in citations:
                print(f"  - [{cit['document_name']}] Page {cit['page_number']}")
        else:
            print("❌ Retrieval Failed (0 chunks used).")
            print(f"Message: {result.get('answer')}")
            
        print(f"\nAnswer:\n{result.get('answer')}")
        
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="tell me about Charlie", help="Query to test")
    args = parser.parse_args()
    
    asyncio.run(test_retrieval(args.query))

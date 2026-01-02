#!/usr/bin/env python3
"""
Debug Script: Multi-Entity Retrieval.
Checks if "Who is in Marketing?" returns all people (Charlie, Bob, Alice?) or just one.
"""
import sys
import os
import asyncio
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from loguru import logger

# Force DEBUG level to see reranker scores
logger.remove()
logger.add(sys.stderr, level="DEBUG")

async def test_multi_entity(query="who is in Marketing?"):
    print(f"\n{'='*60}")
    print(f"Testing Query: {query}")
    print(f"{'='*60}")
    
    db = SessionLocal()
    try:
        rag = RAGService(db=db)
        
        # 1. Expand
        expanded = await rag._expand_query(query)
        print(f"Expanded: {expanded}")
        
        # 2. Retrieve
        # Use a high top_k to see what's in the vector store
        # passing top_k=20 explicitly
        result = await rag.query(user_id=1, query=query, top_k=20)
        
        candidates = result.get('chunks_retrieved', 0)
        final_count = result.get('chunks_after_filtering', 0)
        citations = result.get('citations', [])
        
        print(f"\nCandidates (Pre-Rerank): {candidates}")
        print(f"Final Chunks (Post-Rerank): {len(citations)}")
        
        # Inspect content to see who was found
        people_found = set()
        for cit in citations:
            # This requires access to the chunk content which isn't in citations list usually, 
            # but let's see if we can infer or print from logs.
            # Actually, let's print the chunks from the Service logs (which we enabled DEBUG for)
            pass

        print(f"\nAnswer:\n{result.get('answer')}")

    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="who is in Marketing?", help="Query to test")
    args = parser.parse_args()
    
    asyncio.run(test_multi_entity(args.query))

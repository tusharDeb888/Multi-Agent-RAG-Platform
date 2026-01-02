#!/usr/bin/env python3
"""
Debug Script: Inspect Reranker Scores and Boost Logic.
"""
import sys
import os
import asyncio
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from loguru import logger

# Force DEBUG level
logger.remove()
logger.add(sys.stderr, level="DEBUG")

async def trace_scores(query="tell me about Helen"):
    print(f"\n{'='*60}")
    print(f"Testing Query: {query}")
    print(f"{'='*60}")
    
    db = SessionLocal()
    try:
        rag = RAGService(db=db)
        
        # 1. Expand (Visualize expansion)
        expanded = await rag._expand_query(query)
        print(f"Expanded: {expanded}")
        
        # 2. Trace Retrieval
        # We'll use the internal _retrieve_context logic here but reproduced to print scores
        # actually, simply calling .query() with DEBUG logs enabled above should be enough
        # as the service logs scores for every chunk.
        
        await rag.query(user_id=1, query=query, top_k=20)

    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="tell me about Helen", help="Query to test")
    args = parser.parse_args()
    
    asyncio.run(trace_scores(args.query))

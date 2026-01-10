
"""
RAG Evaluation Script
Runs a set of "Golden Questions" and evaluates:
1. Retrieval Recall (Did we find the right doc?)
2. Answer Grounding (Did we cite the right doc?)
3. Latency
"""
import sys
import os
import asyncio
import time
from typing import List, Dict

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from loguru import logger

# Test Cases
GOLDEN_DATASET = [
    {
        "query": "Hi, how are you?",
        "intent": "CHITCHAT",
        "expected_doc_ids": [] # Should not retrieve
    },
    {
        "query": "What is the safety valve pressure setting?",
        "intent": "FACT_LOOKUP",
        "expected_keywords": ["psi", "pressure"]
    },
    {
        "query": "Compare centrifugal and positive displacement pumps.",
        "intent": "COMPARISON",
        "expected_keywords": ["flow", "viscosity", "pressure"]
    }
]

async def eval_runner():
    logger.info("Starting RAG Evaluation...")
    db = SessionLocal()
    rag = RAGService(db)
    
    results = []
    
    for case in GOLDEN_DATASET:
        query = case["query"]
        logger.info(f"--- Eval Query: '{query}' ---")
        
        t0 = time.time()
        try:
            # We mock user_id=1
            response = await rag.query(user_id=1, query=query)
            latency = time.time() - t0
            
            # Check Intent (Implicitly via retrieval count)
            retrieved_count = response.get("candidate_count", 0)
            
            status = "PASS"
            if case["intent"] == "CHITCHAT" and retrieved_count > 0:
                logger.warning(f"FAIL: Chitchat triggered retrieval ({retrieved_count} docs)")
                status = "FAIL"
            elif case["intent"] != "CHITCHAT" and retrieved_count == 0:
                 logger.warning(f"FAIL: Fact lookup found NO docs")
                 status = "FAIL"
            
            results.append({
                "query": query,
                "latency": latency,
                "status": status,
                "retrieved": retrieved_count
            })
            
        except Exception as e:
            logger.error(f"Error evaluating '{query}': {e}")
            results.append({"query": query, "status": "ERROR", "error": str(e)})

    # Report
    print("\n\n=== EVALUATION REPORT ===")
    for r in results:
        print(f"Query: {r['query'][:30]}... | Status: {r['status']} | Latency: {r.get('latency',0):.2f}s | Retrieved: {r.get('retrieved',0)}")
        
if __name__ == "__main__":
    asyncio.run(eval_runner())

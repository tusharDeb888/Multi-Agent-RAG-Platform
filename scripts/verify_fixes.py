import asyncio
import time
import sys
import re
from loguru import logger
from app.core.database import SessionLocal
from app.domain.models import User
from app.application.services.rag_service import RAGService
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.faiss_store import FAISSVectorStore

# Helper to init singletons explicitly (simulating Startup)
def init_system():
    logger.info("Initializing System (Warmup)...")
    t0 = time.time()
    LLMFactory.warmup()
    # Mocking singletons for script
    global embed_service, vector_store
    embed_service = EmbeddingService()
    vector_store = FAISSVectorStore(dimension=384) 
    t1 = time.time()
    logger.info(f"System Warmup took {t1 - t0:.2f}s")
    
async def run_verification():
    db = SessionLocal()
    try:
        # Get admin user
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
             logger.error("Admin user 'admin' not found! Please seed DB.")
             return

        # 1. Initialize Service with Singletons
        rag_service = RAGService(
            db, 
            llm_adapter=LLMFactory.create_llm_adapter(),
            embedding_service=embed_service,
            vector_store=vector_store
        )
        
        # 2. Test 1: Hallucination Refusal & Zero Citation
        logger.info("\n--- TEST 1: Hallucination Check (Capital of Mars) ---")
        t0 = time.time()
        result_mars = await rag_service.query(user.id, "What is the capital of Mars?", top_k=5)
        t1 = time.time()
        
        if "No grounded information found" in result_mars['answer'] or \
           "No matching information found" in result_mars['answer'] or \
           "cannot find the answer" in result_mars['answer']:
             logger.success("✅ Passed: System refused to answer hallucination request.")
             if len(result_mars['citations']) == 0:
                 logger.success("✅ Passed: Citations list is empty for refusal.")
             else:
                 logger.error(f"❌ Failed: Citations list NOT empty for refusal ({len(result_mars['citations'])}).")
        else:
             logger.error(f"❌ Failed: System attempted to answer: {result_mars['answer']}")

        # 3. Test 2: Effective Citation Binding (DSA)
        logger.info("\n--- TEST 2: Effective Citation Binding (DSA - Fresh V2) ---")
        t0 = time.time()
        # Query known to exist in docs - Fresh to bypass cache
        result_warm = await rag_service.query(user.id, "sliding window pattern mechanism details V2", top_k=5) 
        t1 = time.time()
        latency = t1 - t0
        logger.info(f"Query Time: {latency:.3f}s")
        logger.info(f"Answer: {result_warm['answer']}")
        
        # Check for citation parsing
        parsed_ids = re.findall(r'\[\[(\d+)\]\]', result_warm['answer'])
        if parsed_ids:
            logger.success(f"✅ Passed: Answer contains inline citations: {parsed_ids}")
            
            # Check if citations match
            returned_ids = {str(c['chunk_id']) for c in result_warm['citations']}
            returned_docs = {c['document_name'] for c in result_warm['citations']}
            cited_set = set(parsed_ids)
            
            if cited_set.issubset(returned_ids):
                 logger.success(f"✅ Passed: Returned citations {returned_ids} include explicitly cited IDs {cited_set}.")
            else:
                 logger.warning(f"⚠️ Warning: Mismatch. Parsed: {cited_set}, Returned: {returned_ids}")
                 
            # False Positive Check
            for doc in returned_docs:
                if "Superstore" in doc:
                    logger.error(f"❌ Failed: Irrelevant document 'Superstore' found in citations for DSA query.")
                else:
                    logger.info(f"Cited Document: {doc}")
                    
        else:
            logger.warning("⚠️ Warning: No inline citations found in answer. Fallback mode likely active.")
            logger.info(f"Fallback Citations: {len(result_warm['citations'])}")
            
        # ALWAYS check for false positives
        returned_docs = {c['document_name'] for c in result_warm['citations']}
        for doc in returned_docs:
            if "Superstore" in doc:
                logger.error(f"❌ Failed: Irrelevant document 'Superstore' found in citations (Fallback or Explicit).")
            else:
                logger.info(f"Cited Document: {doc}")

    except Exception as e:
        logger.error(f"Verification Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    init_system()
    asyncio.run(run_verification())

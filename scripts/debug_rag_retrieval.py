import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk
from app.application.services.rag_service import RAGService
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever
from app.core.config import get_settings
from loguru import logger

async def main():
    logger.info("DEBUGging Retrieval Flow...")
    
    query = "zomato fy24 financial report"
    user_id = 1
    
    # 1. Test Identification
    logger.info("--- Step 1: Identification ---")
    with SessionLocal() as db:
        rag = RAGService(db=db, vector_store=None, llm_adapter=None) # Mock dependencies
        
        target_id = rag._identify_target_document_sync(query, user_id)
        logger.info(f"Identified Target ID: {target_id}")
    
    if not target_id:
        logger.error("Identification Failed!")
        return
        
    # 2. Check Chunks in DB
    logger.info("--- Step 2: Database Chunks ---")
    with SessionLocal() as db:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == target_id).limit(5).all()
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == target_id).count()
        chunk_ids = [c.id for c in chunks]
        logger.info(f"Document {target_id} has {chunk_count} chunks in DB.")
        logger.info(f"Sample IDs: {chunk_ids}")
        if chunks:
            logger.info(f"Sample Content (Chunk {chunks[0].id}): {chunks[0].content[:200]}...")

    # 3. Check BM25 Index
    logger.info("--- Step 3: BM25 Search ---")
    bm25 = SparseBM25Retriever()
    settings = get_settings()
    await bm25.load(settings.bm25_index_path)
    
    # Debug Vocab
    if bm25.state:
        vocab = bm25.state.vectorizer.vocabulary_
        logger.info(f"Vocab Size: {len(vocab)}")
        logger.info(f"'zomato' key in vocab? {'zomato' in vocab}")
        logger.info(f"'financial' key in vocab? {'financial' in vocab}")
        
        # Transform Query Check
        q_vec = bm25.state.vectorizer.transform([query])
        logger.info(f"Query Vector Non-Zero: {q_vec.nonzero()[1]}")
    
    results = await bm25.search(query, top_k=50)
    logger.info(f"BM25 Raw Results Count: {len(results)}")
    
    # Check overlap
    bm25_ids = {int(r[0]) for r in results}
    doc_ids_set = set(chunk_ids)
    
    overlap = bm25_ids.intersection(doc_ids_set)
    logger.info(f"Overlap between BM25 results and Document Chunks: {len(overlap)}")
    if overlap:
        logger.info(f"Top 5 matching IDs: {list(overlap)[:5]}")
    else:
        logger.warning("No overlap! BM25 is returning chunks from other docs, or nothing relevant.")

    # 4. Check Config
    logger.info("--- Step 4: Config Check ---")
    logger.info(f"BM25 Path: {settings.bm25_index_path}")

if __name__ == "__main__":
    asyncio.run(main())

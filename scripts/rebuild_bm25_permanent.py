
import sys
import os
import logging
import asyncio
from datetime import datetime

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import DocumentChunk
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever

async def rebuild_bm25():
    logger.info("🚀 Starting BM25 Rebuild...")
    
    db = SessionLocal()
    try:
        # Fetch ALl IDs and Content
        # For 60k chunks, we can load into memory to ensure safety
        logger.info("Querying DB...")
        query = db.query(DocumentChunk.id, DocumentChunk.content).all()
        logger.info(f"Loaded {len(query)} chunks from DB.")
        
        corpus_ids = [q[0] for q in query]
        corpus_text = [q[1] for q in query]
        
        bm25 = SparseBM25Retriever()
        
        logger.info("fitting BM25...")
        await bm25.fit(corpus_text, corpus_ids)
        
        from app.core.config import get_settings
        settings = get_settings()
        save_path = f"{settings.index_storage_path}.bm25_index"
        logger.info(f"Saving to {save_path}...")
        await bm25.save(save_path)
        
        logger.info("✅ BM25 Rebuild Complete & Saved.")
        
    except Exception as e:
        logger.error(f"❌ Failed: {e}", exc_info=True)
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(rebuild_bm25())

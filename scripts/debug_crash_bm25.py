
import sys
import os
import logging
from datetime import datetime

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import DocumentChunk
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever

def debug_bm25_crash():
    logger.info("Starting BM25 Crash Debug Script")
    
    try:
        db = SessionLocal()
        count = db.query(DocumentChunk).count()
        logger.info(f"Connected to DB. Found {count} chunks.")
        
        bm25 = SparseBM25Retriever()
        
        logger.info("Starting generator...")
        collected_ids = []
        
        def content_stream():
            logger.info("Querying DB...")
            query = db.query(DocumentChunk.id, DocumentChunk.content).order_by(DocumentChunk.id).yield_per(1000)
            i = 0
            for chunk_id, content in query:
                collected_ids.append(chunk_id)
                i += 1
                if i % 100 == 0:
                    logger.info(f"Yielded {i} chunks")
                yield content
        
        logger.info("Calling fit()...")
        t0 = datetime.utcnow()
        
        # This is where it supposedly crashes
        bm25.fit(content_stream(), collected_ids)
        
        duration = (datetime.utcnow() - t0).total_seconds()
        logger.info(f"Fit completed in {duration:.2f}s")
        logger.info(f"Vocab size: {len(bm25.vectorizer.vocabulary_)}")
        logger.info("SUCCESS: Did not crash.")
        
    except Exception as e:
        logger.error(f"CRASHED/FAILED: {e}", exc_info=True)

if __name__ == "__main__":
    debug_bm25_crash()

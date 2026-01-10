import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.domain.models import DocumentChunk
from app.domain.repositories.chunk_repository import ChunkRepository
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever
from app.core.config import get_settings
from loguru import logger

async def main():
    logger.info("Starting BM25 Index Rebuild...")
    settings = get_settings()
    
    # 1. Fetch Data
    with SessionLocal() as db:
        logger.info("Fetching all chunks from database...")
        chunks = db.query(DocumentChunk).all()
        logger.info(f"Fetched {len(chunks)} chunks.")
        
        if not chunks:
            logger.warning("No chunks found. Exiting.")
            return

        texts = [c.content for c in chunks]
        ids = [c.id for c in chunks]

    # 2. Build Index
    bm25 = SparseBM25Retriever()
    logger.info("Fitting BM25 index...")
    await bm25.fit(texts, ids)
    
    # 3. Save
    logger.info(f"Saving index to {settings.bm25_index_path}...")
    await bm25.save(settings.bm25_index_path)
    logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())

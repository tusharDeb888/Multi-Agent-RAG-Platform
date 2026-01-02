
"""
Migration Script: FAISS/Oracle -> Milvus.
Strategy:
1. Iterate all Document Chunks from Oracle (SoR).
2. For each chunk:
   - Try to fetch existing vector from FAISS (Speed).
   - If missing, regenerate using EmbeddingService (Correctness).
3. Upsert to Milvus in batches.
"""
import sys
import os
import asyncio
from typing import List
import numpy as np
from sqlalchemy.orm import Session
from loguru import logger
from tqdm import tqdm

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.domain.models import DocumentChunk
from app.infrastructure.vector_store.faiss_store import FAISSVectorStore
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.infrastructure.embeddings.embedding_service import EmbeddingService

BATCH_SIZE = 100

def migrate():
    logger.info("Starting Migration to Milvus...")
    
    # 1. Initialize Services
    settings = get_settings()
    db: Session = SessionLocal()
    
    # FAISS (Source 1)
    try:
        faiss_store = FAISSVectorStore(dimension=settings.vector_dimension)
        logger.info("FAISS Store loaded.")
    except Exception as e:
        logger.warning(f"Could not load FAISS store: {e}. Will regenerate all embeddings.")
        faiss_store = None
        
    # Milvus (Target)
    try:
        milvus_store = MilvusVectorStore()
        logger.info("Milvus Store connected.")
    except Exception as e:
        logger.error(f"Could not connect to Milvus: {e}")
        return

    # Embedding Service (Source 2 - Fallback)
    embedding_service = EmbeddingService()
    
    try:
        # 2. Get Total Count
        total_chunks = db.query(DocumentChunk).count()
        logger.info(f"Total Chunks to Migrate: {total_chunks}")
        
        # 3. Iterate in Batches
        offset = 0
        pbar = tqdm(total=total_chunks, desc="Migrating")
        
        while offset < total_chunks:
            # Fetch Batch from Oracle
            chunks = db.query(DocumentChunk).offset(offset).limit(BATCH_SIZE).all()
            if not chunks:
                break
                
            vectors_to_add = []
            ids_to_add = []
            metadata_to_add = []
            
            # Prepare Batch
            texts_to_embed = []
            text_indices = []
            
            for i, chunk in enumerate(chunks):
                vec = None
                # Try FAISS
                if faiss_store:
                    try:
                        vec = faiss_store.get_vector(chunk.id)
                    except:
                        pass
                
                if vec is not None:
                    vectors_to_add.append(vec)
                    ids_to_add.append(chunk.id)
                    metadata_to_add.append({"document_id": chunk.document_id})
                else:
                    # Queue for generation
                    texts_to_embed.append(chunk.content)
                    text_indices.append(i) # Track which chunk this is
            
            # Flush Generation Queue
            if texts_to_embed:
                # logger.info(f"Regenerating {len(texts_to_embed)} embeddings...")
                new_vectors = embedding_service.embed_batch(texts_to_embed)
                
                for idx_in_batch, vec in zip(text_indices, new_vectors):
                    chunk = chunks[idx_in_batch]
                    vectors_to_add.append(np.array(vec))
                    ids_to_add.append(chunk.id)
                    metadata_to_add.append({"document_id": chunk.document_id})
            
            # Upsert to Milvus
            if vectors_to_add:
                milvus_store.add_vectors(
                    vectors=np.array(vectors_to_add),
                    ids=ids_to_add,
                    metadata=metadata_to_add
                )
            
            offset += BATCH_SIZE
            pbar.update(len(chunks))
            
        pbar.close()
        logger.success("Migration Complete!")
        
    except Exception as e:
        logger.error(f"Migration Failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()

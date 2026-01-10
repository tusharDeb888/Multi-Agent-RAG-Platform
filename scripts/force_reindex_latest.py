
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import Document
from app.domain.repositories.chunk_repository import ChunkRepository
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore

async def reindex_latest():
    db = SessionLocal()
    try:
        # Get latest doc
        latest_doc = db.query(Document).order_by(Document.id.desc()).first()
        if not latest_doc:
            print("No documents found.")
            return

        print(f"Re-indexing Document ID {latest_doc.id}: {latest_doc.filename}")
        
        # Get chunks via relationship
        chunks = latest_doc.chunks
        print(f"Found {len(chunks)} chunks in DB.")
        
        if not chunks:
            print("No chunks to index.")
            return
            
        # Initialize Services
        embedding_service = EmbeddingService()
        vector_store = MilvusVectorStore() # Direct instantiation
        
        # Embed
        texts = [c.content for c in chunks]
        metadatas = [{"document_id": c.document_id, "page_number": c.page_number or 1, "chunk_id": c.id} for c in chunks]
        
        print("Generating embeddings...")
        embeddings = await asyncio.to_thread(embedding_service.embed_batch, texts)
        
        # Add to Store
        print(f"Upserting {len(embeddings)} vectors to Milvus...")
        ids = [str(c.id) for c in chunks] # Milvus expects string IDs often, or ints depending on schema. Our schema uses Int64 usually.
        # Checking IngestionService... it passes chunk.id (int)
        ids_int = [c.id for c in chunks]
        
        await asyncio.to_thread(vector_store.add_vectors, embeddings, ids_int, metadatas)
        
        print("✅ Re-indexing complete.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(reindex_latest())

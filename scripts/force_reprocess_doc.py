import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk, DocumentStatus
from app.application.services.ingestion_service import IngestionService
from loguru import logger

async def main():
    doc_id = 63
    logger.info(f"Force Reprocessing Document {doc_id} to fix garbage text...")
    
    with SessionLocal() as db:
        # 1. Check Document
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.error("Document not found!")
            return
            
        logger.info(f"Target: {doc.filename} at {doc.file_path}")
        if not os.path.exists(doc.file_path):
             logger.error("File does not exist on disk! Cannot re-ingest.")
             return

        # 2. Delete Chunks
        deleted = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
        logger.info(f"Deleted {deleted} garbage chunks.")
        
        # 3. Reset Status
        doc.status = DocumentStatus.PENDING
        doc.error_message = None
        db.commit()
        
        # 4. Trigger Ingestion (Async wrapper)
        # We need to instantiate IngestionService
        # We can mock other services since we just want text extraction + chunking
        # Actually IngestionService needs vector_store to save? 
        # Yes, process_document calls vector_store.add_documents
        
        # We'll use the factory or standard init
        from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
        from app.infrastructure.embeddings.embedding_service import EmbeddingService
        
        # We assume Vector Store is ready or we just fail at that step, 
        # but at least text chunks will be regenerated in DB.
        # Actually verify_status_fix.py might be improved for this.
        
        # Let's try to run the full service if possible.
        
        service = IngestionService(db=db)
        # We manually inject dependencies if needed or let it use defaults/mock
        # IngestionService.__init__ uses default factory if None? 
        # No, defaults are None.
        # It creates them? 
        # Looking at code: __init__(self, db, embedding_service=None, vector_store=None)
        # It doesn't auto-create them in __init__.
        # But process_document uses self.vector_store if available.
        
        # We need real embedding/vector store to perform full ingestion.
        # Let's initialize them.
        embed = EmbeddingService()
        vstore = MilvusVectorStore()
        
        service = IngestionService(db, embedding_service=embed, vector_store=vstore)
        
        logger.info("Starting Ingestion pipeline...")
        await service.process_document(doc.id)
        
        logger.info("Reprocessing Complete.")

if __name__ == "__main__":
    asyncio.run(main())

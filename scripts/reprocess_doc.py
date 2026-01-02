import sys
import os
import asyncio
from sqlalchemy.orm import Session

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk, DocumentStatus
from app.application.services.ingestion_service import IngestionService

def reprocess_document(doc_id: int):
    print(f"--- Reprocessing Document ID {doc_id} ---")
    db = SessionLocal()
    try:
        # Enable logging
        from loguru import logger
        logger.remove()
        logger.add("debug_ingest.log", level="INFO")
        logger.add(sys.stderr, level="INFO")
        
        # Clear previous log
        with open("debug_ingest.log", "w") as f: f.write("")
        
        from app.core.config import get_settings
        settings = get_settings()
        print(f"DEBUG: ENABLE_OCR = {settings.enable_ocr}")
        print(f"DEBUG: VISION_PROVIDER = {settings.vision_provider}")
        
        # 1. Get Document
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            print("❌ Document not found")
            return

        # Debug: Check one chunk before deleting
        chunk = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).first()
        if chunk:
            t = chunk.content
            print(f"DEBUG: First chunk content (len={len(t)}): {t[:50]}...")
        
        print(f"Found: {doc.filename} (Current Status: {doc.status})")

        # 2. Delete existing chunks
        chunks_deleted = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
        print(f"Deleted {chunks_deleted} existing chunks.")
        
        # Reset Status
        doc.status = DocumentStatus.PENDING
        doc.processed_at = None
        doc.error_message = None
        db.commit()
        
        # 3. Trigger Processing
        ingestion = IngestionService(db)
        print("Starting ingestion process...")
        
        success = ingestion.process_document(doc_id)
        
        if success:
            print("✅ Reprocessing Completed Successfully!")
        else:
            print("❌ Reprocessing Failed.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    did = 8
    reprocess_document(did)

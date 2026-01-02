#!/usr/bin/env python3
"""
Re-ingest documents script.
Forces re-processing of specific documents by ID or filename.
"""
import sys
import os
import asyncio
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.application.services.ingestion_service import IngestionService
from app.domain.repositories.document_repository import DocumentRepository
from app.domain.models import Document, DocumentStatus
from loguru import logger

def reingest_excel_files():
    db = SessionLocal()
    try:
        repo = DocumentRepository(db)
        ingestion = IngestionService(db)
        
        # Find all Excel documents
        docs = db.query(Document).filter(Document.filename.like('%.xlsx')).all()
        logger.info(f"Found {len(docs)} Excel documents to re-ingest")
        
        for doc in docs:
            logger.info(f"Re-ingesting: {doc.filename} (ID: {doc.id})")
            
            # Reset status
            doc.status = DocumentStatus.PENDING
            db.commit()
            
            # Process synchronously for script
            success = ingestion.process_document(doc.id)
            if success:
                logger.info(f"Successfully re-ingested {doc.filename}")
            else:
                logger.error(f"Failed to re-ingest {doc.filename}")

    finally:
        db.close()

if __name__ == "__main__":
    reingest_excel_files()

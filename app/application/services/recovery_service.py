"""
Recovery Service for handling interrupted background tasks.
"""
import asyncio
from loguru import logger
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentStatus
from app.application.services.ingestion_service import IngestionService
from app.domain.repositories.document_repository import DocumentRepository

class RecoveryService:
    """
    Service to recover system state after restart or crash.
    """
    
    @staticmethod
    async def recover_stuck_documents():
        """
        Finds documents stuck in EXTRACTING or PENDING state and re-queues them.
        Run this on application startup.
        """
        logger.info("🚑 Starting Recovery Service for stuck documents...")
        
        try:
            # We use a synchronous session in a thread for DB query
            stuck_docs = await asyncio.to_thread(RecoveryService._get_stuck_docs_sync)
            
            if not stuck_docs:
                logger.info("✅ No stuck documents found.")
                return

            logger.info(f"⚠️ Found {len(stuck_docs)} stuck documents. Attempting recovery...")
            
            for doc_id, status in stuck_docs:
                # Launch a background task for each
                # We do not await them here, we fire and forget (managed by asyncio loop)
                asyncio.create_task(RecoveryService._recover_single_document(doc_id, status))
                
        except Exception as e:
            logger.error(f"❌ Recovery Service failed: {e}")

    @staticmethod
    def _get_stuck_docs_sync():
        """Sync DB access to find docs."""
        with SessionLocal() as db:
            # Find docs that are EXTRACTING (crashed mid-process) 
            # OR PENDING (sitting in queue but queue was lost on restart)
            # We can optionally limit to those older than X minutes, but on startup, 
            # ANY stuck doc implies it wasn't finished.
            
            # Note: If we have multiple replicas, this might race. 
            # Assuming Single-Instance or Sticky processing for now.
            # Enterprise Fix: Use distributed lock (Redis) or 'processing_started_at' timestamp.
            
            docs = db.query(Document)\
                .filter(Document.status.in_([DocumentStatus.EXTRACTING, DocumentStatus.PENDING]))\
                .all()
            return [(d.id, d.status) for d in docs]

    @staticmethod
    async def _recover_single_document(doc_id: int, old_status: DocumentStatus):
        """Process a single stuck document."""
        try:
            logger.info(f"🔄 Recovering Doc ID {doc_id} (Was {old_status})...")
            
            # If it was EXTRACTING, it might be in a bad state. 
            # Resetting to PENDING is safest.
            if old_status == DocumentStatus.EXTRACTING:
                await asyncio.to_thread(RecoveryService._reset_status_sync, doc_id)
            
            # Re-process
            # We create a fresh DB session for the service
            with SessionLocal() as db:
                ingestion_service = IngestionService(db)
                success = await ingestion_service.process_document(doc_id)
                
            if success:
                 logger.info(f"✅ Recovered Doc ID {doc_id} successfully.")
            else:
                 logger.warning(f"⚠️ Failed to recover Doc ID {doc_id}.")

        except Exception as e:
            logger.error(f"❌ Failed to recover Doc ID {doc_id}: {e}")

    @staticmethod
    def _reset_status_sync(doc_id: int):
        with SessionLocal() as db:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.status = DocumentStatus.PENDING
                doc.error_message = None # Clear previous errors
                db.commit()

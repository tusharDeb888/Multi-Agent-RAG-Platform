
import asyncio
import os
import sys
import logging
from datetime import datetime

# Adjust path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal, engine, Base
from app.domain.models import Document, DocumentStatus, ClassificationLevel
from app.application.services.ingestion_service import IngestionService
from app.domain.repositories.document_repository import DocumentRepository

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_debug():
    print("--- Starting Debug for Processing Hang ---")
    
    # 1. Setup DB
    db = SessionLocal()
    
    # 2. Check for stalled documents
    repo = DocumentRepository(db)
    stalled = db.query(Document).filter(Document.status == DocumentStatus.PROCESSING).all()
    print(f"Found {len(stalled)} stalled documents.")
    for doc in stalled:
        print(f" - ID: {doc.id}, File: {doc.filename}, Started: {doc.uploaded_at}")
        
    # 3. Create a fresh test document
    test_file = "test_ocr.pdf"
    if not os.path.exists(test_file):
        print(f"Error: {test_file} not found locally.")
        return

    # Create dummy entry
    doc = Document(
        filename="debug_hang_test.pdf",
        original_filename="debug_hang_test.pdf",
        file_path=os.path.abspath(test_file),
        file_size_mb=0.1,
        mime_type="application/pdf",
        classification=ClassificationLevel.INTERNAL,
        status=DocumentStatus.PENDING,
        uploaded_by=1 # Assuming user 1 exists, or nullable
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    print(f"Created Test Document ID: {doc.id}")
    
    # 4. Run Processing
    service = IngestionService(db)
    
    print("Invoking process_document...")
    start_time = datetime.now()
    
    try:
        # We need to run this with a timeout to detect hangs
        task = asyncio.create_task(service.process_document(doc.id))
        
        # Wait for 60 seconds max
        await asyncio.wait_for(task, timeout=60.0)
        print("Processing Completed Successfully!")
        
    except asyncio.TimeoutError:
        print("!!! TIMEOUT DETECTED !!!")
        print("Processing hung for > 60 seconds.")
        # We can't easily see stacktrace of hung task without invasive debugging,
        # but we know IT HUNG.
        
    except Exception as e:
        print(f"Processing Failed with Error: {e}")
        import traceback
        traceback.print_exc()

    end_time = datetime.now()
    print(f"Duration: {(end_time - start_time).total_seconds()}s")

    # Check status
    db.refresh(doc)
    print(f"Final Status: {doc.status}")
    if doc.error_message:
        print(f"Error Message: {doc.error_message}")

if __name__ == "__main__":
    asyncio.run(run_debug())

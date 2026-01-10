import sys
import os
import asyncio
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentStatus
from app.application.services.ingestion_service import IngestionService

async def reingest_zomato():
    """Re-ingest the Zomato document with proper extraction"""
    db = SessionLocal()
    try:
        # Find the document
        doc = db.query(Document).filter(Document.id == 90).first()
        if not doc:
            print("❌ Document ID 90 not found")
            return
            
        print(f"📄 Found: {doc.filename}")
        print(f"   Current status: {doc.status}")
        print(f"   Total pages: {doc.total_pages}")
        
        # Reset status to trigger re-processing
        print("\n🔄 Resetting document status to PENDING...")
        doc.status = DocumentStatus.PENDING
        doc.processed_at = None
        doc.error_message = None
        db.commit()
        
        # Trigger ingestion
        print("🚀 Starting ingestion service...")
        ingestion_service = IngestionService(db)
        
        print(f"📥 Processing document ID {doc.id}...")
        await ingestion_service.process_document(doc.id)
        
        # Check result
        db.refresh(doc)
        print(f"\n✅ Processing complete!")
        print(f"   New status: {doc.status}")
        print(f"   Total pages: {doc.total_pages}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(reingest_zomato())

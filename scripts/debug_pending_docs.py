import sys
import os
import asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings
from app.domain.models import Document, DocumentStatus

async def main():
    settings = get_settings()
    print(f"Database URL: {settings.database_url}")
    
    # Use sync engine for this script
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        # Check PENDING
        stmt = select(Document).where(Document.status == DocumentStatus.PENDING)
        pending_docs = session.execute(stmt).scalars().all()
        
        print(f"\n--- Found {len(pending_docs)} PENDING Documents ---")
        for doc in pending_docs:
            print(f"ID: {doc.id} | Filename: {doc.filename} | Uploaded: {doc.uploaded_at}")
            
        # Check FAILED (to see if they actually failed but UI shows pending? Unlikely)
        stmt_failed = select(Document).where(Document.status == DocumentStatus.FAILED)
        failed_docs = session.execute(stmt_failed).scalars().all()
        
        print(f"\n--- Recent FAILED Documents (Last 5) ---")
        for doc in failed_docs[-5:]:
            print(f"ID: {doc.id} | Filename: {doc.filename} | Error: {doc.error_message}")

        # Check EXTRACTING/EMBEDDING
        stmt_active = select(Document).where(Document.status.in_([DocumentStatus.EXTRACTING, DocumentStatus.EMBEDDING]))
        active_docs = session.execute(stmt_active).scalars().all()
        print(f"\n--- Active Processing (EXTRACTING/EMBEDDING) ---")
        for doc in active_docs:
             print(f"ID: {doc.id} | Status: {doc.status} | Filename: {doc.filename}")

if __name__ == "__main__":
    asyncio.run(main())


import sys
import os
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentStatus
from sqlalchemy import desc

def debug_failures():
    db = SessionLocal()
    try:
        # Get last 5 failing docs
        failed_docs = db.query(Document).filter(
            Document.status == DocumentStatus.FAILED
        ).order_by(desc(Document.uploaded_at)).limit(5).all()
        
        print(f"Found {len(failed_docs)} recently failed documents:")
        for doc in failed_docs:
            print(f"---")
            print(f"ID: {doc.id}")
            print(f"Filename: {doc.filename}")
            print(f"Error Message: {doc.error_message}")
            print(f"Uploaded At: {doc.uploaded_at}")
    finally:
        db.close()

if __name__ == "__main__":
    debug_failures()

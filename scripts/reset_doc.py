from app.core.database import SessionLocal
from app.domain.models import Document, DocumentStatus
from sqlalchemy import text

def reset_document(doc_id):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = "Processing timed out or was manually cancelled."
            db.commit()
            print(f"Document {doc_id} reset to FAILED.")
        else:
            print("Document not found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_document(6)

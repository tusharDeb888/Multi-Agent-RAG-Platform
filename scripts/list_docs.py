from app.core.database import SessionLocal
from app.domain.models import Document

def list_documents():
    db = SessionLocal()
    try:
        documents = db.query(Document).all()
        print(f"Found {len(documents)} documents:")
        for doc in documents:
            print(f"ID: {doc.id}, Filename: {doc.filename}, Status: {doc.status}, Uploaded: {doc.uploaded_at}")
    finally:
        db.close()

if __name__ == "__main__":
    list_documents()

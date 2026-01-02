
from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk

def inspect_chunks():
    db = SessionLocal()
    try:
        # Get last uploaded document
        doc = db.query(Document).order_by(Document.id.desc()).first()
        if not doc:
            print("No documents found.")
            return

        print(f"Document ID: {doc.id}, Filename: {doc.filename}")
        
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).order_by(DocumentChunk.chunk_index).limit(20).all()
        
        print(f"Found {len(chunks)} chunks (showing first 20):")
        for c in chunks:
            print(f"Chunk {c.chunk_index}: Page {c.page_number} | Content Preview: {c.content[:50]}...")
            
    finally:
        db.close()

if __name__ == "__main__":
    inspect_chunks()

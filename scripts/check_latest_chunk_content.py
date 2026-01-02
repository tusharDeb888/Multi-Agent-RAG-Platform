
from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk

def check_latest_content():
    db = SessionLocal()
    try:
        # Get the most recent document
        doc = db.query(Document).order_by(Document.id.desc()).first()
        if not doc:
            print("No documents found.")
            return

        print(f"Latest Document ID: {doc.id}")
        print(f"Filename: {doc.filename}")
        print(f"Status: {doc.status}")
        
        # Get chunks
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).limit(5).all()
        print(f"\nScanning first 5 chunks of Document {doc.id}...")
        
        for c in chunks:
            print(f"\n--- Chunk {c.chunk_index} (Page {c.page_number}) ---")
            print(f"Content Length: {len(c.content)}")
            print(f"Vision Tag Present: {'[VISUAL DESCRIPTION]' in c.content}")
            print(f"Garbage Present (LLLL): {'LLLL' in c.content}")
            print(f"Snippet:\n{c.content[:200]}...")
            if '[VISUAL DESCRIPTION]' in c.content:
                print(f"\nVision Content:\n{c.content.split('[VISUAL DESCRIPTION]:')[1][:200]}...")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_latest_content()

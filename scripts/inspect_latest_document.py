import sys
import os
from sqlalchemy import desc

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk

def inspect_latest():
    db = SessionLocal()
    try:
        # Get latest doc
        doc = db.query(Document).order_by(desc(Document.id)).first()
        if not doc:
            print("No documents found.")
            return

        print(f"Latest Document: ID={doc.id}, Filename='{doc.filename}', Status='{doc.status}'")
        
        # Get chunks
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
        print(f"Total Chunks: {len(chunks)}")
        
        found_ethan = False
        print("\n--- Content Sample (First 3 Chunks) ---")
        for i, chunk in enumerate(chunks[:3]):
            print(f"Chunk {i}: {chunk.content[:200]}...")
            
        print("\n--- Keyword Search: 'Ethan' ---")
        for chunk in chunks:
            if "ethan" in chunk.content.lower():
                print(f"✅ Found 'Ethan' in Chunk {chunk.id} (Page {chunk.page_number})")
                print(f"Context: ...{chunk.content[max(0, chunk.content.lower().find('ethan')-50):chunk.content.lower().find('ethan')+50]}...")
                found_ethan = True
                
        if not found_ethan:
            print("❌ Keyword 'Ethan' NOT found in any chunk.")
            print("Possible causes: OCR failure, Parsing error, or file is truly empty/image-only without OCR.")

    finally:
        db.close()

if __name__ == "__main__":
    inspect_latest()

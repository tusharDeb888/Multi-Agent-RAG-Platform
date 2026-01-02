import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy import or_

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk

def check_document():
    print("--- Inspecting 'dsa pattern' Document ---")
    db = SessionLocal()
    try:
        # 1. Find the document
        doc = db.query(Document).filter(
            or_(
                Document.filename.ilike("%dsa%"),
                Document.filename.ilike("%pattern%")
            )
        ).first()
        
        if not doc:
            print("❌ Document NOT found in DB matching 'dsa' or 'pattern'")
            return
            
        print(f"✅ Found Document: ID={doc.id}, Filename='{doc.filename}'")
        
        # Check file existence
        import os
        if os.path.exists(doc.file_path):
             print(f"✅ File exists at: {doc.file_path}")
        else:
             print(f"❌ File missing at: {doc.file_path}")

        # 2. Check Chunks
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
        print(f"   Total Chunks: {len(chunks)}")
        
        found_term = False
        for chunk in chunks:
            if "happy number" in chunk.content.lower():
                print(f"   🎯 Found 'Happy Number' in Chunk {chunk.id} (Index {chunk.chunk_index})")
                found_term = True
            
            # Print content IF it's likely a vision description, or just sample it
            if "[VISUAL DESCRIPTION]" in chunk.content or "[IMAGE DESCRIPTION]" in chunk.content:
                 print(f"   👁️ Vision Content Detected in Chunk {chunk.id}:")
                 print(chunk.content[:200] + "...")
            elif len(chunks) < 5 or chunk.chunk_index < 2:
                 # Print first few chunks anyway
                 print(f"   --- Chunk {chunk.id} ({len(chunk.content)} chars) ---")
                 print(chunk.content[:100] + "...")
                 
        if not found_term:
            print("❌ Term 'Happy Number' NOT found in any chunk content.")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_document()

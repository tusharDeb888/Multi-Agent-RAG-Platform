
import sys
import os
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import DocumentChunk

def check_content():
    db = SessionLocal()
    try:
        print("Searching chunks for 'Budget'...")
        chunks = db.query(DocumentChunk).filter(DocumentChunk.content.ilike("%Budget%")).all()
        print(f"Found {len(chunks)} chunks.")
        for c in chunks[:3]:
            print(f"--- Chunk {c.id} (Doc {c.document_id}) ---")
            print(c.content[:200] + "...")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_content()


import sys
import os
from sqlalchemy import text
sys.path.append(os.getcwd())
from app.core.database import SessionLocal

def check():
    db = SessionLocal()
    try:
        print("--- Debugging DB ---")
        # Check MAX ID
        res = db.execute(text("SELECT MAX(id) FROM document_chunks")).scalar()
        print(f"MAX(id): {res}")
        
        # Check Doc 113
        count = db.execute(text("SELECT COUNT(*) FROM document_chunks WHERE document_id = 113")).scalar()
        print(f"Doc 113 Chunks: {count}")
        
        if count > 0:
             # Show IDs
             rows = db.execute(text("SELECT id, chunk_index FROM document_chunks WHERE document_id = 113 LIMIT 5")).fetchall()
             for r in rows:
                 print(f" - Row: {r}")
                 
        # Check if ID 100000 exists
        exists = db.execute(text("SELECT * FROM document_chunks WHERE id = 200000")).fetchone()
        print(f"ID 200000 exists? {exists}")
        
    finally:
        db.close()

if __name__ == "__main__":
    check()

import sys
import os
from sqlalchemy import text
from app.core.database import SessionLocal

def check_doc_status(filename_part):
    db = SessionLocal()
    try:
        query = text("SELECT id, filename, status, error_message, uploaded_at, processed_at FROM documents WHERE filename LIKE :fname")
        result = db.execute(query, {"fname": f"%{filename_part}%"}).fetchone()
        
        if result:
            print(f"Document Found: {result[1]} (ID: {result[0]})")
            print(f"Status: {result[2]}")
            print(f"Error Message: {result[3]}")
            print(f"Created: {result[4]}")
            print(f"Processed: {result[5]}")
        else:
            print("Document not found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_doc_status("Operating-system")

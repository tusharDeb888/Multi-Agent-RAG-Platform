
"""
Script to clear all Documents and related data from the database.
Preserves Users, Roles, and Departments.
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.domain.models import (
    Document, DocumentChunk, DocumentAccessPolicy, 
    ChunkAccessPolicy, document_departments
)
from sqlalchemy import delete

def clear_documents():
    db = SessionLocal()
    try:
        print("Clearing database document tables...")
        
        # Deleting in order of dependency (although cascades might handle it, explicit is safer/clearer)
        
        # 1. Chunk Policies
        num_cp = db.query(ChunkAccessPolicy).delete()
        print(f"Deleted {num_cp} Chunk Access Policies")
        
        # 2. Document Policies
        num_dp = db.query(DocumentAccessPolicy).delete()
        print(f"Deleted {num_dp} Document Access Policies")
        
        # 3. Document Chunks (and their Vectors - Vector store cleanup handled separately usually, but here we just do DB)
        num_chunks = db.query(DocumentChunk).delete()
        print(f"Deleted {num_chunks} Document Chunks")
        
        # 4. Document Departments (Association Table)
        # SQLAlchemy Core delete for Table object
        stmt = delete(document_departments)
        result = db.execute(stmt)
        print(f"Deleted {result.rowcount} Document-Department associations")
        
        # 5. Documents
        num_docs = db.query(Document).delete()
        print(f"Deleted {num_docs} Documents")
        
        db.commit()
        print("Successfully cleared all document data.")
        
    except Exception as e:
        print(f"Error clearing database: {e}")
        db.rollback()
    finally:
        db.close()

def clear_physical_files():
    print("\nClearing physical files...")
    
    # 1. Uploads
    upload_dir = "data/uploads"
    if os.path.exists(upload_dir):
        count = 0
        for f in os.listdir(upload_dir):
            path = os.path.join(upload_dir, f)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    count += 1
            except Exception as e:
                print(f"Failed to delete {path}: {e}")
        print(f"Deleted {count} files from {upload_dir}")
        
    # 2. FAISS Index
    faiss_paths = ["data/faiss_index.index", "data/faiss_index.bm25.pkl", "data/faiss_index.json"]
    for path in faiss_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Deleted {path}")
            except Exception as e:
                 print(f"Failed to delete {path}: {e}")
                 
    # 3. Milvus Lite
    milvus_paths = ["milvus.db", "milvus.db.lock"]
    for path in milvus_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Deleted {path}")
            except Exception as e:
                 print(f"Failed to delete {path}: {e}")

if __name__ == "__main__":
    confirm = input("Are you sure you want to delete ALL documents AND physical files? (y/n): ")
    if confirm.lower() == 'y':
        clear_documents()
        clear_physical_files()
    else:
        print("Cancelled.")

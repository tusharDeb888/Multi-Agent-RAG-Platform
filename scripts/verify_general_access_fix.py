import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.domain.models import Department, Document, DocumentStatus, ClassificationLevel, document_departments
from app.domain.repositories.document_repository import DocumentRepository

def verify():
    db = SessionLocal()
    try:
        # 1. ensure Departments exist
        it_dept = db.query(Department).filter(Department.name == "IT").first()
        if not it_dept:
            it_dept = Department(name="IT")
            db.add(it_dept)
        
        gen_dept = db.query(Department).filter(Department.name == "General").first()
        if not gen_dept:
            gen_dept = Department(name="General")
            db.add(gen_dept)
            
        db.commit()
        db.refresh(it_dept)
        db.refresh(gen_dept)
        
        print(f"IT Dept ID: {it_dept.id}")
        print(f"General Dept ID: {gen_dept.id}")

        # 2. Create Dummy Document tagged "General"
        doc = Document(
            filename="general_policy.pdf",
            original_filename="general_policy.pdf",
            file_path="/tmp/dummy.pdf",
            file_size_mb=1.0,
            mime_type="application/pdf",
            status=DocumentStatus.SEARCHABLE,
            uploaded_by=1, # Admin
            content_hash="dummyhashesgeneral"
        )
        doc.departments = [gen_dept]
        
        # Check if exists to avoid clutter
        existing = db.query(Document).filter(Document.content_hash == "dummyhashesgeneral").first()
        if existing:
            db.delete(existing)
            db.commit()
            
        db.add(doc)
        db.commit()
        db.refresh(doc)
        print(f"Created General Doc: {doc.id} ({doc.filename})")
        
        # 3. Test Repository Method
        repo = DocumentRepository(db)
        
        # Case A: User in "IT"
        print("\n--- Testing Access for IT User ---")
        docs_it = repo.get_by_department("IT")
        ids_it = [d.id for d in docs_it]
        print(f"IDs accessible to IT: {ids_it}")
        
        if doc.id in ids_it:
            print("SUCCESS: General document IS visible to IT.")
        else:
            print("FAILURE: General document is NOT visible to IT.")

        # Case B: User in "HR" (Just to be sure checks global)
        print("\n--- Testing Access for HR User ---")
        docs_hr = repo.get_by_department("HR")
        ids_hr = [d.id for d in docs_hr]
        
        if doc.id in ids_hr:
            print("SUCCESS: General document IS visible to HR.")
        else:
             print("FAILURE: General document is NOT visible to HR.")
             
        # Cleanup
        db.delete(doc)
        db.commit()

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify()

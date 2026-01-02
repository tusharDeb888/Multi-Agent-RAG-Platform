
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to import app logic
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.domain.models import User, Document, Department, ClassificationLevel, DocumentAccessPolicy

settings = get_settings()

def verify_multi_dept_rbac():
    print("--- Starting Multi-Department RBAC Verification ---")
    
    # Connect
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # 1. Setup Data - Departments
        print("\n1. Setting up Departments...")
        
        def get_or_create_dept(name):
            dept = db.query(Department).filter(Department.name == name).first()
            if not dept:
                dept = Department(name=name, description="Test Dept")
                db.add(dept)
                db.commit()
                db.refresh(dept)
            return dept
        
        dept_eng = get_or_create_dept("Engineering")
        dept_hr = get_or_create_dept("HR")
        dept_gen = get_or_create_dept("General")
        
        # 2. Setup Data - Users
        print("2. Setting up Users...")
        
        def reset_user(username, dept_id):
            u = db.query(User).filter(User.username == username).first()
            if u:
                u.department_id = dept_id
            else:
                 u = User(
                    username=username, 
                    email=f"{username}@example.com", 
                    hashed_password="hash", 
                    full_name=username,
                    department_id=dept_id
                )
                 db.add(u)
            db.commit()
            db.refresh(u)
            return u
            
        user_eng = reset_user("user_eng", dept_eng.id)
        user_hr = reset_user("user_hr", dept_hr.id)
        
        # 3. Setup Data - Documents
        print("3. Setting up Documents...")
        
        def create_doc(filename, depts):
            d = db.query(Document).filter(Document.filename == filename).first()
            if d:
                # Update depts
                d.departments = depts
            else:
                d = Document(
                    filename=filename,
                    original_filename=filename,
                    file_path=f"/tmp/{filename}",
                    file_size_mb=1.0,
                    mime_type="application/pdf",
                    uploaded_by=user_eng.id
                )
                d.departments = depts
                db.add(d)
                
            db.commit()
            db.refresh(d)
            return d

        doc_eng = create_doc("eng_only.pdf", [dept_eng])
        doc_hr = create_doc("hr_only.pdf", [dept_hr])
        doc_multi = create_doc("multi_dept.pdf", [dept_eng, dept_hr])
        doc_gen = create_doc("general.pdf", [dept_gen])
        
        # 4. Verify Access logic via Repository
        print("\n4. Verifying Access via Repository...")
        from app.domain.repositories.access_policy_repository import DocumentAccessPolicyRepository
        repo = DocumentAccessPolicyRepository(db)
        
        def check_access(user, doc, expected_access, label):
            accessible_ids = repo.get_accessible_documents(user.id, user.department_id, [])
            has_access = doc.id in accessible_ids
            # print(f"  Debug: User {user.username} (Dept {user.department_id}) Access IDs: {accessible_ids}")
            
            status = "OPEN" if has_access else "LOCKED"
            expected = "OPEN" if expected_access else "LOCKED"
            result = "PASS" if has_access == expected_access else "FAIL"
            print(f"  {label:<40} Actual: {status:<8} Expected: {expected:<8} -> {result}")
            if result == "FAIL":
                raise Exception(f"Verification Failed for {label}")

        # Eng User Tests
        check_access(user_eng, doc_eng, True, "Engineering User -> Engineering Doc")
        check_access(user_eng, doc_hr, False, "Engineering User -> HR Doc")
        check_access(user_eng, doc_multi, True, "Engineering User -> Multi (Eng+HR) Doc")
        check_access(user_eng, doc_gen, True, "Engineering User -> General Doc") # Implicit General Access
        
        # HR User Tests
        check_access(user_hr, doc_eng, False, "HR User -> Engineering Doc")
        check_access(user_hr, doc_hr, True, "HR User -> HR Doc")
        check_access(user_hr, doc_multi, True, "HR User -> Multi (Eng+HR) Doc")
        check_access(user_hr, doc_gen, True, "HR User -> General Doc")
        
        print("\n✅ Multi-Department Verification Passed!")
        
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close() # Clean closure

if __name__ == "__main__":
    verify_multi_dept_rbac()

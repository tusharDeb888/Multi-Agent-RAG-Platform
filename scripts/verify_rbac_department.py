
import sys
import os
import secrets
from sqlalchemy.orm import Session
from datetime import datetime

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal, Base, engine
from app.domain.models import User, Department, Document, DocumentAccessPolicy, UserRole, UserRoleMap, Role
from app.application.services.rbac_service import RBACService
from app.core.security import get_password_hash

def setup_test_data(db: Session):
    print("Setting up test data...")
    
    # Create Roles if not exist
    roles = [UserRole.EMPLOYEE, UserRole.DEPARTMENT_ADMIN, UserRole.SUPER_ADMIN]
    for role_enum in roles:
        r = db.query(Role).filter(Role.name == role_enum.value).first()
        if not r:
            db.add(Role(name=role_enum.value, description=f"{role_enum.value} role"))
    db.commit()

    # Create Departments
    dept_hr = db.query(Department).filter(Department.name == "HR").first()
    if not dept_hr:
        dept_hr = Department(name="HR", description="Human Resources")
        db.add(dept_hr)
    
    dept_it = db.query(Department).filter(Department.name == "IT").first()
    if not dept_it:
        dept_it = Department(name="IT", description="Information Technology")
        db.add(dept_it)
    
    db.commit()
    db.refresh(dept_hr)
    db.refresh(dept_it)
    
    # Create Users
    # User A in HR
    user_hr = db.query(User).filter(User.username == "hr_user").first()
    if not user_hr:
        user_hr = User(
            username="hr_user",
            email="hr@example.com",
            hashed_password=get_password_hash("password"),
            full_name="HR User",
            department_id=dept_hr.id,
            is_active=True
        )
        db.add(user_hr)
        db.commit()
        db.refresh(user_hr)
        # Assign Role
        role_emp = db.query(Role).filter(Role.name == UserRole.EMPLOYEE.value).first()
        db.add(UserRoleMap(user_id=user_hr.id, role_id=role_emp.id))
        db.commit()
        
    # User B in IT
    user_it = db.query(User).filter(User.username == "it_user").first()
    if not user_it:
        user_it = User(
            username="it_user",
            email="it@example.com",
            hashed_password=get_password_hash("password"),
            full_name="IT User",
            department_id=dept_it.id,
            is_active=True
        )
        db.add(user_it)
        db.commit()
        db.refresh(user_it)
        role_emp = db.query(Role).filter(Role.name == UserRole.EMPLOYEE.value).first()
        db.add(UserRoleMap(user_id=user_it.id, role_id=role_emp.id))
        db.commit()

    # Create Document in HR
    doc_hr = db.query(Document).filter(Document.filename == "hr_policy.pdf").first()
    if not doc_hr:
        doc_hr = Document(
            filename="hr_policy.pdf",
            original_filename="hr_policy.pdf",
            file_path="/tmp/hr_policy.pdf",
            file_size_mb=1.0,
            mime_type="application/pdf",
            department_id=dept_hr.id,
            uploaded_by=user_hr.id,
            total_pages=1
        )
        db.add(doc_hr)
        db.commit()
        db.refresh(doc_hr)
        
        # Add Policy: Access for HR department
        policy = DocumentAccessPolicy(
            document_id=doc_hr.id,
            department_id=dept_hr.id,
            access_type="read"
        )
        db.add(policy)
        db.commit()
        
    return user_hr, user_it, doc_hr

def verify_rbac():
    db = SessionLocal()
    try:
        # Ensure tables exist (might need explicit create if not using migration)
        Base.metadata.create_all(bind=engine)
        
        user_hr, user_it, doc_hr = setup_test_data(db)
        
        rbac_service = RBACService(db)
        
        print(f"\n--- Verification: Document {doc_hr.filename} (Dept: HR) ---")
        
        # Check HR User access
        access_hr = rbac_service.can_access_document(user_hr.id, doc_hr.id)
        print(f"User {user_hr.username} (Dept: HR) access: {access_hr}")
        assert access_hr == True, "HR User should access HR document"
        
        # Check IT User access
        access_it = rbac_service.can_access_document(user_it.id, doc_hr.id)
        print(f"User {user_it.username} (Dept: IT) access: {access_it}")
        assert access_it == False, "IT User should NOT access HR document"
        
        print("\n✅ RBAC Verification Passed!")
        
    except AssertionError as e:
        print(f"\n❌ Verification Failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    verify_rbac()


import asyncio
import logging
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.domain.models import User, Document, Department, UserRole, document_departments
from app.application.services.rbac_service import RBACService
from app.domain.repositories.access_policy_repository import DocumentAccessPolicyRepository

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_rbac_issue():
    db: Session = SessionLocal()
    try:
        logger.info("--- Starting RBAC Reproduction Test ---")
        
        # 1. Setup Data
        # Ensure Departments Exist
        hr_dept = db.query(Department).filter(Department.name == "HR").first()
        eng_dept = db.query(Department).filter(Department.name == "Engineering").first()
        
        if not hr_dept or not eng_dept:
            logger.error("Departments missing! Please seed DB.")
            return

        # Create/Get Users
        hr_user = db.query(User).filter(User.username == "hr_user_test").first()
        if not hr_user:
            hr_user = User(
                username="hr_user_test", email="hr@test.com", 
                hashed_password="pw", full_name="HR User",
                department_id=hr_dept.id, 
                roles=[] # Need to add role but basic user usually has employee
            )
            db.add(hr_user)
            db.commit()
            db.refresh(hr_user)
            
        # Create/Get Engineering Document
        eng_doc = db.query(Document).filter(Document.filename == "eng_secret.txt").first()
        if not eng_doc:
            eng_doc = Document(
                filename="eng_secret.txt", 
                original_filename="eng_secret.txt",
                content_hash="secret123",
                mime_type="text/plain",
                file_path="/tmp/dummy_eng_secret.txt",
                file_size_mb=0.1,
                uploaded_by=hr_user.id
            )
            eng_doc.departments = [eng_dept]
            db.add(eng_doc)
            db.commit()
            db.refresh(eng_doc)
            
        logger.info(f"HR User ID: {hr_user.id}, Dept: {hr_user.department.name}")
        logger.info(f"Eng Doc ID: {eng_doc.id}, Depts: {[d.name for d in eng_doc.departments]}")
        
        # 2. Check Access via Repo (Low Level)
        repo = DocumentAccessPolicyRepository(db)
        # Assuming empty roles for now or basic
        accessible_ids = repo.get_accessible_documents(
            user_id=hr_user.id,
            user_department_id=hr_user.department_id,
            user_role_ids=[]
        )
        
        can_see_low_level = eng_doc.id in accessible_ids
        logger.info(f"Repo Check: HR User can see Eng Doc? {can_see_low_level}")
        if can_see_low_level:
             logger.error("❌ FAILURE: Implicit Access Logic returned forbidden document!")
        
        # 3. Check Access via Service (High Level)
        rbac = RBACService(db)
        can_access = rbac.can_access_document(hr_user.id, eng_doc.id)
        logger.info(f"Service Check: HR User can access Eng Doc? {can_access}")
        
        if can_access:
            logger.error("❌ FAILURE: RBAC Service allowed access!")
        else:
            logger.info("✅ SUCCESS: Access Denied.")
            
        # 4. Test Sync Issue (Admin Update)
        # Simulate Admin moving Doc to HR
        logger.info("\n--- Testing Sync Issue ---")
        logger.info("Simulating Admin update: Moving Eng Doc to HR Department...")
        eng_doc.departments = [hr_dept] # Direct DB update simulating API
        db.commit()
        
        # Immediate Check
        accessible_ids_after = repo.get_accessible_documents(
            user_id=hr_user.id,
            user_department_id=hr_user.department_id,
            user_role_ids=[]
        )
        can_see_after = eng_doc.id in accessible_ids_after
        logger.info(f"After Update: HR User can see Doc? {can_see_after}")
        
        if can_see_after:
            logger.info("✅ SUCCESS: Sync worked (Implicit logic is immediate).")
        else:
             logger.error("❌ FAILURE: Sync failed (Doc not visible after move).")

    except Exception as e:
        logger.error(f"Test crashed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_rbac_issue()

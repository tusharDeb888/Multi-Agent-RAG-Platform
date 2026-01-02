
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.domain.models import User, Department, UserRole, Role, UserRoleMap, Document, DocumentStatus, document_departments
from app.application.services.rbac_service import RBACService
from app.domain.repositories.document_repository import DocumentRepository

def test_rbac_isolation():
    db = SessionLocal()
    try:
        print("🧪 Setting up RBAC Isolation Test...")
        
        # 1. Create Departments
        print("   Creating departments 'HR' and 'IT'...")
        hr_dept = db.query(Department).filter_by(name="HR_TEST").first()
        if not hr_dept:
            hr_dept = Department(name="HR_TEST")
            db.add(hr_dept)
            
        it_dept = db.query(Department).filter_by(name="IT_TEST").first()
        if not it_dept:
            it_dept = Department(name="IT_TEST")
            db.add(it_dept)
            
        gen_dept = db.query(Department).filter_by(name="General").first()
        if not gen_dept:
            gen_dept = Department(name="General")
            db.add(gen_dept)
            
        db.commit()
        db.refresh(hr_dept)
        db.refresh(it_dept)
        
        # 2. Create Users
        print("   Creating users 'hr_user' and 'it_user'...")
        
        # Role: Employee
        emp_role = db.query(Role).filter_by(name=UserRole.EMPLOYEE).first()
        if not emp_role:
            emp_role = Role(name=UserRole.EMPLOYEE)
            db.add(emp_role)
            db.commit()
            
        # HR User
        hr_user = db.query(User).filter_by(username="hr_user_test").first()
        if not hr_user:
            hr_user = User(
                username="hr_user_test", email="hr@test.com", 
                full_name="HR Test", hashed_password="pw",
                department_id=hr_dept.id
            )
            db.add(hr_user)
            db.flush()
            # Assign Role
            db.add(UserRoleMap(user_id=hr_user.id, role_id=emp_role.id))
            
        # IT User
        it_user = db.query(User).filter_by(username="it_user_test").first()
        if not it_user:
            it_user = User(
                username="it_user_test", email="it@test.com", 
                full_name="IT Test", hashed_password="pw",
                department_id=it_dept.id
            )
            db.add(it_user)
            db.flush()
            # Assign Role
            db.add(UserRoleMap(user_id=it_user.id, role_id=emp_role.id))
            
        db.commit()
        db.refresh(hr_user)
        db.refresh(it_user)
        
        # 3. Create Documents
        print("   Creating documents 'HR_Doc.txt', 'IT_Doc.txt', 'General_Doc.txt'...")
        doc_repo = DocumentRepository(db)
        
        # HR Doc
        hr_doc = Document(
            filename="HR_Doc_Test.txt", original_filename="HR_Doc_Test.txt", 
            file_path="dummy", file_size_mb=0, mime_type="text/plain",
            uploaded_by=hr_user.id, status=DocumentStatus.SEARCHABLE
        )
        hr_doc.departments = [hr_dept] # M2M
        db.add(hr_doc)
        
        # IT Doc
        it_doc = Document(
            filename="IT_Doc_Test.txt", original_filename="IT_Doc_Test.txt", 
            file_path="dummy", file_size_mb=0, mime_type="text/plain",
            uploaded_by=it_user.id, status=DocumentStatus.SEARCHABLE
        )
        it_doc.departments = [it_dept] # M2M
        db.add(it_doc)
        
        # General Doc
        gen_doc = Document(
            filename="Gen_Doc_Test.txt", original_filename="Gen_Doc_Test.txt", 
            file_path="dummy", file_size_mb=0, mime_type="text/plain",
            uploaded_by=hr_user.id, status=DocumentStatus.SEARCHABLE
        )
        gen_doc.departments = [gen_dept] # M2M
        db.add(gen_doc)
        
        db.commit()
        
        # Refresh to get IDs
        db.refresh(hr_doc)
        db.refresh(it_doc)
        db.refresh(gen_doc)
        
        print("\n🔎 Verifying Access Policies via RBACService...")
        rbac = RBACService(db)
        
        # Test 1: HR User Access
        print(f"\n[Test 1] Checking HR User (Dept: {hr_user.department.name})")
        accessible_docs_hr = rbac.doc_policy_repo.get_accessible_documents(
            user_id=hr_user.id,
            user_department_id=hr_user.department_id,
            user_role_ids=rbac.get_user_roles(hr_user.id)
        )
        
        print(f"   HR Doc ID: {hr_doc.id}")
        print(f"   IT Doc ID: {it_doc.id}")
        print(f"   General Doc ID: {gen_doc.id}")
        
        # Verify M2M relationships
        print("\n   Verifying M2M links:")
        print(f"   HR Doc Depts: {[d.name for d in hr_doc.departments]}")
        print(f"   IT Doc Depts: {[d.name for d in it_doc.departments]}")
        
        print("\n🔎 Verifying Access Policies via RBACService...")
        rbac = RBACService(db)
        
        # Test 1: HR User Access
        print(f"\n[Test 1] Checking HR User (Dept: {hr_user.department.name}, ID: {hr_user.department_id})")
        accessible_docs_hr = rbac.doc_policy_repo.get_accessible_documents(
            user_id=hr_user.id,
            user_department_id=hr_user.department_id,
            user_role_ids=rbac.get_user_roles(hr_user.id)
        )
        
        print(f"   HR User can see docs: {accessible_docs_hr}")
        
        # Soft Assertions
        errors = []
        if hr_doc.id not in accessible_docs_hr:
            errors.append(f"❌ HR User CANNOT see HR Doc {hr_doc.id}")
        else:
            print("✅ HR User sees HR Doc")
            
        if gen_doc.id not in accessible_docs_hr:
            errors.append(f"❌ HR User CANNOT see General Doc {gen_doc.id}")
        else:
            print("✅ HR User sees General Doc")
        
        if it_doc.id in accessible_docs_hr:
             errors.append(f"❌ BREACH: HR User CAN see IT Doc {it_doc.id}")
        else:
             print("✅ Success: HR User CANNOT see IT Doc")
             
        # Test 2: IT User Access
        print(f"\n[Test 2] Checking IT User (Dept: {it_user.department.name}, ID: {it_user.department_id})")
        accessible_docs_it = rbac.doc_policy_repo.get_accessible_documents(
            user_id=it_user.id,
            user_department_id=it_user.department_id,
            user_role_ids=rbac.get_user_roles(it_user.id)
        )
        
        print(f"   IT User can see docs: {accessible_docs_it}")
        
        if it_doc.id not in accessible_docs_it:
            errors.append(f"❌ IT User CANNOT see IT Doc {it_doc.id}")
        if hr_doc.id in accessible_docs_it:
             errors.append(f"❌ BREACH: IT User CAN see HR Doc {hr_doc.id}")
        
        if errors:
            print("\n❌ TEST FAILED with errors:")
            for e in errors:
                print(e)
        else:
            print("\n🎉 ALL TESTS PASSED. RBAC Logic seems correct.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        try:
           # Clean simulated data? Or leave for manual inspection 
           # Ideally delete
           pass
        except:
            pass
        db.close()

if __name__ == "__main__":
    test_rbac_isolation()

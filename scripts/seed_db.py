"""
Seed database with initial data.
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.domain.models import User, UserRole, Role, UserRoleMap, Department
from app.core.security import get_password_hash

def seed_data():
    db = SessionLocal()
    try:
        # Create Tables
        from app.core.database import engine, Base
        print("Dropping existing tables...")
        Base.metadata.drop_all(bind=engine)
        print("Creating tables...")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully.")

        # Create Roles
        roles = [
            {"name": UserRole.SUPER_ADMIN, "description": "Super Administrator"},
            {"name": UserRole.DEPARTMENT_ADMIN, "description": "Department Administrator"},
            {"name": UserRole.EMPLOYEE, "description": "Regular Employee"},
            {"name": UserRole.AUDITOR, "description": "System Auditor"},
        ]
        
        for role_data in roles:
            role = db.query(Role).filter(Role.name == role_data["name"]).first()
            if not role:
                role = Role(**role_data)
                db.add(role)
                print(f"Created role: {role_data['name']}")
        
        db.commit()
        
        # Create Users
        users_to_create = [
            {
                "username": "admin",
                "email": "admin@iocl.in",
                "password": "admin",
                "full_name": "Super Admin",
                "department": "IT",
                "role": UserRole.SUPER_ADMIN
            },
            {
                "username": "tushar8888",
                "email": "tushar8888@iocl.in",
                "password": "tushar8888",
                "full_name": "Tushar Deb",
                "department": "Engineering",
                "role": UserRole.EMPLOYEE
            },
            {
                "username": "testuser1",
                "email": "testuser1@iocl.in",
                "password": "testuser1",
                "full_name": "Test User1",
                "department": "HR",
                "role": UserRole.EMPLOYEE
            },
            {
                "username": "testuser2",
                "email": "testuser2@iocl.in",
                "password": "testuser2",
                "full_name": "Test User2",
                "department": "IT",
                "role": UserRole.EMPLOYEE
            }
        ]

        for user_data in users_to_create:
            user = db.query(User).filter(User.username == user_data["username"]).first()
            if not user:
                # Resolve Department
                dept_name = user_data.get("department")
                dept_obj = None
                if dept_name:
                    dept_obj = db.query(Department).filter(Department.name == dept_name).first()
                    if not dept_obj:
                        dept_obj = Department(name=dept_name, description=f"{dept_name} Department")
                        db.add(dept_obj)
                        db.commit()
                        db.refresh(dept_obj)
                
                user = User(
                    username=user_data["username"],
                    email=user_data["email"],
                    hashed_password=get_password_hash(user_data["password"]),
                    full_name=user_data["full_name"],
                    department=dept_obj, # Pass object, not string
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Created user: {user_data['username']}")
                
                # Assign Role
                role_obj = db.query(Role).filter(Role.name == user_data["role"]).first()
                if role_obj:
                    user_role = UserRoleMap(user_id=user.id, role_id=role_obj.id)
                    db.add(user_role)
                    db.commit()
                    print(f"Assigned {user_data['role']} role to {user_data['username']}")
            else:
                print(f"User {user_data['username']} already exists")
            
    except Exception as e:
        print(f"Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()

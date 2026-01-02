import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.domain.models import User
from app.core.security import verify_password, get_password_hash

def check_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if user:
            print(f"User found: {user.username}")
            print(f"Email: {user.email}")
            print(f"Hashed Password: {user.hashed_password}")
            
            is_valid = verify_password("admin", user.hashed_password)
            print(f"Password 'admin' is valid: {is_valid}")
            
            if not is_valid:
                print("Resetting password to 'admin'...")
                new_hash = get_password_hash("admin")
                user.hashed_password = new_hash
                db.commit()
                print("Password reset complete.")
                
                # Verify again
                is_valid_new = verify_password("admin", new_hash)
                print(f"New password 'admin' is valid: {is_valid_new}")
        else:
            print("User 'admin' not found.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_user()

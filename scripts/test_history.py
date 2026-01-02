import sys
import os

# Add parent directory to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.application.services.audit_service import AuditService
from app.domain.models import User, AuditLog
from datetime import datetime

def test_history():
    db = SessionLocal()
    try:
        # Get admin user
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            print("Admin user not found, cannot test.")
            return

        print(f"Testing history for user: {user.username} (ID: {user.id})")

        audit_service = AuditService(db)
        
        # Check current history
        history = audit_service.get_user_history(user.id)
        print(f"Current history count: {len(history)}")

        # Add a dummy log if empty
        if len(history) == 0:
            print("Adding dummy query log...")
            audit_service.log_query(
                user_id=user.id,
                query_text="Test query for verification",
                response_text="Test response",
                accessed_document_ids=[]
            )
            history = audit_service.get_user_history(user.id)
            print(f"New history count: {len(history)}")
            
        # Verify sorting (descending timestamp)
        if len(history) > 1:
            is_sorted = all(history[i].timestamp >= history[i+1].timestamp for i in range(len(history)-1))
            print(f"History is sorted correctly: {is_sorted}")
        
        # Print top entry
        if history:
            latest = history[0]
            print(f"Latest entry: {latest.query_text} at {latest.timestamp}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_history()

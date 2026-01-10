import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal, engine, Base
from app.domain.models import AuditLog, User
from app.application.services.audit_service import AuditService
from sqlalchemy import text

def test_history():
    db = SessionLocal()
    try:
        # 1. Check if table exists
        print("Checking tables...")
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"Tables found: {tables}")
        
        if "audit_logs" not in tables:
            print("ERROR: 'audit_logs' table missing!")
            return

        # 2. Try simple query
        print("Querying audit logs...")
        logs = db.query(AuditLog).limit(5).all()
        print(f"Found {len(logs)} generic logs.")
        
        # 3. Try service method
        svc = AuditService(db)
        # Assuming user_id 1 exists (admin usually)
        history = svc.get_user_history(user_id=1, limit=10)
        print(f"Found {len(history)} history items for user 1.")
        for h in history:
            print(f"- {h.timestamp}: {h.query_text} -> {h.response_text[:20]}...")
            
    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_history()

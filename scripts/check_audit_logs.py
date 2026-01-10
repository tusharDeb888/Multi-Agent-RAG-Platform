import sys
import os
from sqlalchemy import create_engine, text
from app.core.config import get_settings

# Setup DB connection
settings = get_settings()

def check_audit_logs():
    print(f"Connecting to DB: {settings.database_url}")
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        print("\n--- Last 10 Audit Log Entries ---")
        try:
            # Query audit_logs table
            # Adjust column names based on model if needed, but usually query * works for dump
            result = conn.execute(text("SELECT * FROM audit_logs ORDER BY timestamp DESC FETCH FIRST 10 ROWS ONLY"))
            
            rows = result.fetchall()
            if not rows:
                print("⚠️ No audit logs found!")
            else:
                for row in rows:
                    print(row)
                    
            print(f"\nTotal Logs: {len(rows)}")
        except Exception as e:
            print(f"Error querying audit_logs: {e}")
            # Fallback for SQLite/Postgres limit syntax if Oracle fails (though user said Oracle)
            # Oracle 12c+ supports FETCH FIRST. Old Oracle might need ROWNUM.
            # User said "Oracle (old version)". ROWNUM is safer.
            if "ORA-" in str(e) or "syntax" in str(e).lower():
                 print("Retrying with ROWNUM syntax...")
                 result = conn.execute(text("SELECT * FROM audit_logs WHERE ROWNUM <= 10 ORDER BY timestamp DESC"))
                 for row in result.fetchall():
                     print(row)

if __name__ == "__main__":
    check_audit_logs()

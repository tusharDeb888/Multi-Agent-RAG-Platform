
import sys
import os
from sqlalchemy import inspect, text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def verify_db():
    try:
        print("Connecting to database...")
        with engine.connect() as connection:
            print("Connection successful!")
            
            # Check version
            version = connection.execute(text("SELECT * FROM v$version")).fetchone()
            print(f"Database Version: {version[0] if version else 'Unknown'}")
            
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print("\nExisting Tables:")
            if not tables:
                print("No tables found. (Database might be empty)")
            for table in tables:
                print(f" - {table}")
                
            # Basic schema check
            expected_tables = ["users", "documents", "audit_logs"]
            missing = [t for t in expected_tables if t not in tables and t.upper() not in tables]
            
            if missing:
                print(f"\n[WARNING] Missing expected tables: {missing}")
            else:
                print("\n[SUCCESS] Core schema seems to be present.")

    except Exception as e:
        print(f"\n[ERROR] Database connection failed: {e}")

if __name__ == "__main__":
    verify_db()

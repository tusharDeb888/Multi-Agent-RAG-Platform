import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.core.database import engine

def migrate_title():
    print("Migrating: Adding 'title' column to 'documents' table...")
    with engine.connect() as conn:
        try:
            # Oracle specific check
            conn.execute(text("ALTER TABLE documents ADD title VARCHAR2(255)"))
            conn.commit()
            print("Successfully added 'title' column.")
        except Exception as e:
            if "ORA-01430" in str(e): # Column already exists
                 print("Column 'title' already exists. Skipping.")
            else:
                print(f"Error migrating: {e}")

if __name__ == "__main__":
    migrate_title()


import sys
import os
from sqlalchemy import text, inspect

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.domain.models import Department, Document

def migrate():
    print("Starting Multi-Department Migration...")
    
    # 1. Create new table
    Base.metadata.create_all(bind=engine)
    print("Schema updated (created document_departments if missing).")
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # 2. Check if old column exists
            insp = inspect(engine)
            columns = [c['name'] for c in insp.get_columns('documents')]
            
            if 'department_id' in columns:
                print("Migrating data from documents.department_id to document_departments...")
                
                # Insert into mapping table
                conn.execute(text("""
                    INSERT INTO document_departments (document_id, department_id)
                    SELECT id, department_id 
                    FROM documents 
                    WHERE department_id IS NOT NULL
                """))
                
                # Verify
                count = conn.execute(text("SELECT count(*) FROM document_departments")).scalar()
                print(f"Migrated {count} associations.")
                
                # 3. Drop old column
                print("Dropping documents.department_id...")
                conn.execute(text("ALTER TABLE documents DROP COLUMN department_id"))
            else:
                print("Column department_id not found in documents (already migrated?).")
                
            trans.commit()
            print("Migration successful.")
        except Exception as e:
            trans.rollback()
            print(f"Migration failed: {e}")
            raise

if __name__ == "__main__":
    migrate()

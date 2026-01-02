"""
Migration script to add content_hash to documents table.
"""
import sys
import os
from sqlalchemy import create_engine, text
from app.core.config import get_settings

def migrate():
    settings = get_settings()
    db_url = settings.database_url
    
    print(f"Migrating DB: {db_url}")
    
    if "oracle" in db_url:
        print("Detected Oracle DB...")
        alter_stmt = "ALTER TABLE documents ADD content_hash VARCHAR2(64)"
        # Index on Oracle
        index_stmt = "CREATE INDEX idx_docs_content_hash ON documents(content_hash)"
    else:
        print("Assuming SQLite/Generic DB...")
        alter_stmt = "ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64)"
        index_stmt = "CREATE INDEX idx_docs_content_hash ON documents(content_hash)"
        
    engine = create_engine(db_url)
    with engine.connect() as conn:
        try:
            print(f"Executing: {alter_stmt}")
            conn.execute(text(alter_stmt))
            print(f"Executing: {index_stmt}")
            try:
                conn.execute(text(index_stmt))
            except Exception as e:
                 print(f"Index creation failed (maybe exists?): {e}")

            conn.commit()
            print("Migration successful.")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "ORA-01430" in str(e):
                print("Column already exists.")
            else:
                print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()

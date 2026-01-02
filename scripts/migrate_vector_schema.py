"""
Migration script to add VECTOR column to document_chunks table for Oracle 23ai.
"""
import sys
import os
from sqlalchemy import create_engine, text
from app.core.config import get_settings

def migrate_schema():
    settings = get_settings()
    db_url = settings.database_url
    
    # Check if we are using Oracle
    if "oracle" not in db_url:
        print("Not using Oracle DB. Skipping VECTOR column migration.")
        print(f"Current DB: {db_url}")
        return

    print(f"Migrating DB for Oracle 23ai Vector Search: {db_url}")
    
    # 384 dimensions for all-MiniLM-L6-v2 (default)
    # Adjust if using different model
    vector_dim = settings.vector_dimension 
    
    # Oracle 23ai Syntax: VECTOR(dim, FLOAT32)
    # Note: ADD (col type) is standard
    alter_stmt = f"ALTER TABLE document_chunks ADD (embedding VECTOR({vector_dim}, FLOAT32))"
    
    engine = create_engine(db_url)
    with engine.connect() as conn:
        try:
            print(f"Executing: {alter_stmt}")
            conn.execute(text(alter_stmt))
            conn.commit()
            print("Migration successful: Added embedding column.")
        except Exception as e:
            if "ORA-01430" in str(e) or "duplicate column" in str(e).lower():
                print("Column 'embedding' already exists.")
            else:
                print(f"Migration failed: {e}")
                # It might fail if DB version < 23c. 
                print("ensure your Oracle DB version supports VECTOR type (23ai).")

if __name__ == "__main__":
    migrate_schema()

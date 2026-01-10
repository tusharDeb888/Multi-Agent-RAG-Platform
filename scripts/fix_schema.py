import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.core.database import engine
from loguru import logger

def fix_schema():
    with engine.connect() as conn:
        logger.info("Checking Schema Drift (Round 4)...")
        
        # Helper to add column safely
        def add_column(table, col_def):
            try:
                logger.info(f"Attempting to add column to {table}: {col_def}")
                conn.execute(text(f"ALTER TABLE {table} ADD {col_def}"))
                conn.commit()
                logger.info("Success.")
            except Exception as e:
                # ORA-01430: column already exists
                if "ORA-01430" in str(e) or "duplicate column name" in str(e).lower():
                    logger.info("Column already exists (OK).")
                else:
                    logger.warning(f"Error adding column: {e}")

        # Fix USERS table (Previous Rounds)
        add_column("users", "failed_login_attempts NUMBER DEFAULT 0")
        add_column("users", "department_id NUMBER")
        add_column("users", "last_login TIMESTAMP")
        add_column("users", "clearance_level VARCHAR2(20) DEFAULT 'internal'")
        add_column("users", "username_snapshot VARCHAR2(255)")
        add_column("users", "is_deleted NUMBER(1) DEFAULT 0")
        add_column("users", "updated_at TIMESTAMP")
        add_column("users", "is_active NUMBER(1) DEFAULT 1")
        
        # Fix DOCUMENTS table (Previous Rounds)
        add_column("documents", "parser_version VARCHAR2(50) DEFAULT 'v1.0'")
        add_column("documents", "metadata_json CLOB")
        add_column("documents", "content_hash VARCHAR2(64)")
        add_column("documents", "classification VARCHAR2(20) DEFAULT 'internal'")
        
        # Fix AUDIT_LOGS table (New Errors)
        add_column("audit_logs", "username_snapshot VARCHAR2(255)")
        add_column("audit_logs", "response_text CLOB")
        add_column("audit_logs", "accessed_documents CLOB")
        add_column("audit_logs", "query_text CLOB")

        # Fix DOCUMENT_CHUNKS (Round 6 - ORA-00904)
        add_column("document_chunks", "metadata_json CLOB")

        # Fix DOCUMENTS defaults (Round 5 - ORA-01400)
        try:
            logger.info("Patching DOCUMENTS defaults...")
            conn.execute(text("ALTER TABLE documents MODIFY uploaded_at DEFAULT SYSTIMESTAMP"))
            conn.commit()
            logger.info("Patched documents.uploaded_at default.")
        except Exception as e:
            logger.warning(f"Could not patch documents.uploaded_at: {e}")
            
        try:
            logger.info("Patching USERS defaults...")
            conn.execute(text("ALTER TABLE users MODIFY created_at DEFAULT SYSTIMESTAMP"))
            conn.commit()
            logger.info("Patched users.created_at default.")
        except Exception as e:
             logger.warning(f"Could not patch users.created_at: {e}")

        # Fix DOCUMENT_CHUNKS Defaults (Round 7 - ORA-01400)
        try:
            logger.info("Patching DOCUMENT_CHUNKS defaults...")
            conn.execute(text("ALTER TABLE document_chunks MODIFY created_at DEFAULT SYSTIMESTAMP"))
            conn.commit()
            logger.info("Patched document_chunks.created_at default.")
        except Exception as e:
            logger.warning(f"Could not patch document_chunks.created_at: {e}")

        logger.info("Schema fix complete.")

if __name__ == "__main__":
    fix_schema()

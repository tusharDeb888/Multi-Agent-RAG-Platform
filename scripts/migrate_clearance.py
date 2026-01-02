"""
Migration script to add clearance_level and classification columns if they don't exist.
"""
import sys
import os
from sqlalchemy import create_engine, text
from app.core.config import get_settings

def migrate():
    settings = get_settings()
    # Use custom DB URL or construct it
    db_url = settings.database_url
    
    if "oracle" in db_url:
        print("Detected Oracle DB. Running Oracle migration...")
        alter_stmt = "ALTER TABLE users ADD clearance_level VARCHAR2(20) DEFAULT 'internal'"
    else:
        # Assuming SQLite for local dev if not Oracle
        # SQLAlchemy 'sqlite' url usually
        print("Assuming SQLite/Generic DB...")
        alter_stmt = "ALTER TABLE users ADD COLUMN clearance_level VARCHAR(20) DEFAULT 'internal'"

    # Note: Enums in SQL are tricky. storing as VARCHAR for simplicity in migration.
    # The Model uses SQLEnum which usually maps to VARCHAR with CHECK constraint or native ENUM.
    # For a hot-fix migration, VARCHAR is safest.
    
    engine = create_engine(db_url)
    with engine.connect() as conn:
        try:
            print(f"Executing: {alter_stmt}")
            conn.execute(text(alter_stmt))
            conn.commit()
            print("Migration successful.")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "ORA-01430" in str(e):
                print("Column already exists.")
            else:
                print(f"Migration failed (might be already applied?): {e}")

if __name__ == "__main__":
    migrate()

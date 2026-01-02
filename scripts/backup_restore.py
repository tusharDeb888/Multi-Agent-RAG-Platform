"""
Backup and Restore Utility for IOCL AI Assistant.
Handles Database (JSON dump) and File System (Uploads/FAISS) backups.
"""
import os
import sys
import shutil
import tarfile
import json
import datetime
import logging
from typing import List, Dict, Any
from sqlalchemy import create_engine, text, inspect, MetaData, Table
from sqlalchemy.orm import sessionmaker

# Add parent dir to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import Base

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BACKUP_DIR = "./backups"
DATA_DIR = "./data"
UPLOADS_DIR = "./data/uploads"
FAISS_INDEX = "./data/faiss_index.index"
ENV_FILE = ".env"

TABLES_ORDER = [
    "roles",
    "users",
    "user_role_map",
    "documents",
    "document_chunks",
    "document_access_policies",
    "chunk_access_policies", 
    "audit_logs"
]

def get_db_engine():
    settings = get_settings()
    return create_engine(settings.database_url)

class BackupManager:
    def __init__(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        self.engine = get_db_engine()
        
    def _export_table(self, table_name: str, export_dir: str):
        """Export a single table to JSON."""
        with self.engine.connect() as conn:
            # Check if table exists
            if not inspect(self.engine).has_table(table_name):
                logger.warning(f"Table {table_name} does not exist, skipping.")
                return

            result = conn.execute(text(f"SELECT * FROM {table_name}"))
            rows = [dict(row._mapping) for row in result]
            
            # Serialize dates/binary
            for row in rows:
                for k, v in row.items():
                    if isinstance(v, (datetime.datetime, datetime.date)):
                        row[k] = v.isoformat()
                    # Handle binary/bytes if any (content_hash is string)
            
            file_path = os.path.join(export_dir, f"{table_name}.json")
            with open(file_path, "w") as f:
                json.dump(rows, f, default=str, indent=2)
            logger.info(f"Exported {len(rows)} rows from {table_name}")

    def create_backup(self) -> str:
        """Create a full backup archive."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
        temp_dir = os.path.join(BACKUP_DIR, backup_name)
        os.makedirs(temp_dir)
        
        try:
            # 1. DB Dump
            db_dir = os.path.join(temp_dir, "db")
            os.makedirs(db_dir)
            logger.info("Starting Database Backup...")
            # Get correct order from metadata or manual list? Manual list is safer for restore deps.
            # But specific tables need to be present.
            # Using defined TABLES_ORDER
            for table in TABLES_ORDER:
                self._export_table(table, db_dir)
                
            # 2. Files
            logger.info("Backing up Files...")
            files_dir = os.path.join(temp_dir, "files")
            os.makedirs(files_dir)
            
            # Copy Uploads
            if os.path.exists(UPLOADS_DIR):
                shutil.copytree(UPLOADS_DIR, os.path.join(files_dir, "uploads"))
                
            # Copy FAISS
            # FAISS can be multiple files (.index, .index.bm25.pkl)
            # Copy entire data dir excluding uploads? simpler to be selective.
            if os.path.exists("./data"):
                os.makedirs(os.path.join(files_dir, "data"), exist_ok=True)
                for f in os.listdir("./data"):
                    if f.startswith("faiss_index"):
                        shutil.copy2(os.path.join("./data", f), os.path.join(files_dir, "data", f))
                        
            # Copy .env
            if os.path.exists(ENV_FILE):
                shutil.copy2(ENV_FILE, os.path.join(files_dir, ".env"))

            # 3. Create Archive
            archive_path = os.path.join(BACKUP_DIR, f"{backup_name}.tar.gz")
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(temp_dir, arcname=backup_name)
                
            logger.info(f"Backup created successfully: {archive_path}")
            return archive_path
            
        finally:
            # Cleanup temp dir
            shutil.rmtree(temp_dir)

    def restore_backup(self, archive_path: str):
        """Restore from a backup archive."""
        if not os.path.exists(archive_path):
            raise FileNotFoundError(f"Backup file not found: {archive_path}")
            
        logger.info(f"Restoring from {archive_path}...")
        
        # Extract
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_restore")
        temp_dir = os.path.join(BACKUP_DIR, f"temp_{timestamp}")
        
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=temp_dir)
                
            # Find the root dir inside temp (it was named backup_TIMESTAMP)
            content_dir = os.path.join(temp_dir, os.listdir(temp_dir)[0])
            
            # 1. Restore Files
            logger.info("Restoring Files...")
            files_src = os.path.join(content_dir, "files")
            
            # Restore Uploads
            if os.path.exists(os.path.join(files_src, "uploads")):
                if os.path.exists(UPLOADS_DIR):
                    shutil.rmtree(UPLOADS_DIR)
                shutil.copytree(os.path.join(files_src, "uploads"), UPLOADS_DIR)
                
            # Restore FAISS
            if os.path.exists(os.path.join(files_src, "data")):
                for f in os.listdir(os.path.join(files_src, "data")):
                    shutil.copy2(os.path.join(files_src, "data", f), os.path.join("./data", f))
            
            # 2. Restore DB
            logger.info("Restoring Database...")
            db_src = os.path.join(content_dir, "db")
            
            # Disable constraints? Difficult in generic SQL.
            # Strategy: Delete all data in reverse order, then Insert in order.
            
            meta = MetaData()
            meta.reflect(bind=self.engine)
            
            with self.engine.connect() as conn:
                trans = conn.begin()
                try:
                    # Clean existing data (Risk! But this is Restore)
                    for table_name in reversed(TABLES_ORDER):
                         if table_name in meta.tables:
                             logger.info(f"Truncating {table_name}...")
                             # Oracle doesn't support TRUNCATE with FKs easily without CASCADE
                             # Use Delete
                             conn.execute(text(f"DELETE FROM {table_name}"))
                    
                    # Insert Data
                    for table_name in TABLES_ORDER:
                        json_path = os.path.join(db_src, f"{table_name}.json")
                        if not os.path.exists(json_path):
                            continue
                            
                        with open(json_path, 'r') as f:
                            rows = json.load(f)
                            
                        if not rows:
                            continue
                            
                        if table_name in meta.tables:
                            table = meta.tables[table_name]
                            logger.info(f"Restoring {len(rows)} rows to {table_name}...")
                            
                            # Parse dates back to objects
                            for row in rows:
                                for k, v in row.items():
                                    if isinstance(v, str) and v.count('-') == 2 and 'T' in v:
                                        try:
                                            # Allow both with and without microseconds
                                            row[k] = datetime.datetime.fromisoformat(v)
                                        except ValueError:
                                            pass
                            
                            # Insert chunk by chunk if large?
                            conn.execute(table.insert(), rows)
                            
                    trans.commit()
                    logger.info("Database Restore Complete.")
                    
                except Exception as e:
                    trans.rollback()
                    logger.error(f"Database Restore Failed: {e}")
                    raise
                    
            logger.info("Restore Process Completed Successfully.")

        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

if __name__ == "__main__":
    import sys
    manager = BackupManager()
    
    if len(sys.argv) < 2:
        print("Usage: python backup_restore.py [backup|restore <file>]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "backup":
        print(manager.create_backup())
    elif cmd == "restore":
        if len(sys.argv) < 3:
            print("Usage: python backup_restore.py restore <archive_path>")
            sys.exit(1)
        manager.restore_backup(sys.argv[2])
    else:
        print("Unknown command")

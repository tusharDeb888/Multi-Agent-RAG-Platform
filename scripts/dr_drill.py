"""
Disaster Recovery Drill Automation.
Simulates a catastrophe and validates recovery.
"""
import os
import sys
import shutil
import logging
from scripts.backup_restore import BackupManager, get_db_engine
from sqlalchemy import text

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - DR DRILL - %(message)s')
logger = logging.getLogger(__name__)

def run_drill():
    logger.info(">>> STARTING DISASTER RECOVERY DRILL <<<")
    manager = BackupManager()
    engine = get_db_engine()
    
    # 1. Initial State Check
    logger.info("Step 1: Analyzing baseline state...")
    with engine.connect() as conn:
        doc_count_before = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar()
        user_count_before = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    
    logger.info(f"Baseline: {doc_count_before} documents, {user_count_before} users.")
    
    # 2. Perform Backup
    logger.info("Step 2: Performing Backup...")
    backup_file = manager.create_backup()
    logger.info(f"Backup created at: {backup_file}")
    
    if not os.path.exists(backup_file):
        logger.error("Backup failed to verify file existence!")
        sys.exit(1)
        
    # 3. Simulate CATASTROPHE
    logger.info("Step 3: SIMULATING DISASTER (Deleting Data)...")
    
    # 3a. Drop DB Data
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Delete in reverse dependency order
            conn.execute(text("DELETE FROM audit_logs"))
            conn.execute(text("DELETE FROM chunk_access_policies"))
            conn.execute(text("DELETE FROM document_access_policies"))
            conn.execute(text("DELETE FROM document_chunks"))
            conn.execute(text("DELETE FROM documents"))
            # Keep users for now? No, full disaster.
            # But restoring users might conflict if we are logged in? 
            # We assume offline drill.
            # conn.execute(text("DELETE FROM users")) # Maybe unwise if using system user?
            # Let's stop at documents for now to be safe, or just Documents & Chunks
            trans.commit()
            logger.info("Database wiped (Documents/Chunks/Audit).")
        except Exception as e:
            trans.rollback()
            logger.error(f"Failed to wipe DB: {e}")
            sys.exit(1)
            
    # 3b. Delete Uploads
    uploads_dir = "./data/uploads"
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)
        logger.info("File system wiped (Uploads directory deleted).")
        
    # Verify Destruction
    with engine.connect() as conn:
        doc_count_mid = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    
    if doc_count_mid != 0:
        logger.error("Simulation Failed: Data still exists in DB!")
        sys.exit(1)
        
    logger.info("Disaster Simulation Successful. System is empty.")
    
    # 4. Perform Restore
    logger.info("Step 4: Executing Recovery Protocol...")
    try:
        manager.restore_backup(backup_file)
    except Exception as e:
        logger.error(f"Restore Failed: {e}")
        sys.exit(1)
        
    # 5. Verification
    logger.info("Step 5: Verifying Integrity...")
    with engine.connect() as conn:
        doc_count_after = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    
    logger.info(f"Post-Recovery: {doc_count_after} documents.")
    
    if doc_count_after == doc_count_before:
        logger.info("✅ SUCCESS: Data restored perfectly. RPO/RTO objectives met.")
    else:
        logger.error(f"❌ FAILURE: Data mismatch. Expected {doc_count_before}, got {doc_count_after}.")
        sys.exit(1)
        
    logger.info(">>> DRILL COMPLETE <<<")

if __name__ == "__main__":
    run_drill()

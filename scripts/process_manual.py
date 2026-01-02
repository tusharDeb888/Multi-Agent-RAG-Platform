from app.core.database import SessionLocal
from app.application.services.ingestion_service import IngestionService
from loguru import logger
import sys

# Configure logger to show info
logger.remove()
logger.add(sys.stderr, level="INFO")

def process_manual(doc_id):
    db = SessionLocal()
    try:
        service = IngestionService(db)
        print(f"Processing document {doc_id}...")
        result = service.process_document(doc_id)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    process_manual(3)

import sys
import os
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings
from app.domain.models import Document, DocumentStatus

async def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=10) # 10 mins stuck is enough to fail
    
    with Session() as session:
        # Find stuck docs
        stmt = select(Document).where(
            Document.status.in_([DocumentStatus.PENDING, DocumentStatus.EXTRACTING, DocumentStatus.EMBEDDING]),
            Document.uploaded_at < cutoff_time
        )
        stuck_docs = session.execute(stmt).scalars().all()
        
        if not stuck_docs:
            print("No stuck documents found (older than 10 mins).")
            return

        print(f"Found {len(stuck_docs)} stuck documents.")
        
        for doc in stuck_docs:
            print(f"Fail-Loop: Marking Doc {doc.id} ({doc.filename}) as FAILED. Stuck in {doc.status} since {doc.uploaded_at}.")
            doc.status = DocumentStatus.FAILED
            doc.error_message = "Processing timed out (Stuck Task)"
            doc.processed_at = datetime.utcnow()
            
        session.commit()
        print("Cleanup complete.")

if __name__ == "__main__":
    asyncio.run(main())

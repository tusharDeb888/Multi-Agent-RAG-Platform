from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from app.application.services.audit_service import AuditService
from app.domain.models import User
from loguru import logger
import sys

# Configure logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

import asyncio

async def test_rag_flow_async():
    db = SessionLocal()
    try:
        # Get admin user
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            print("Admin user not found")
            return

        rag_service = RAGService(db)
        audit_service = AuditService(db)

        print("--- Testing RAG Query ---")
        result = await rag_service.query(
            user_id=user.id,
            query="dsa patterns",
            top_k=5
        )
        print("RAG Result keys:", result.keys())
        print("Answer length:", len(result["answer"]))
        print("Answer:", result["answer"][:100] + "...")
        print("Citations:", len(result["citations"]))
        
        print("--- Testing Audit Log ---")
        audit_service.log_query(
            user_id=user.id,
            query_text="dsa patterns",
            response_text=result["answer"],
            accessed_document_ids=[c["document_id"] for c in result["citations"]]
        )
        print("Audit log created successfully")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_rag_flow_async())

import sys
import os
import asyncio
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_query():
    print("🔍 Testing: 'FY24 Zomato financial report'")
    
    db = SessionLocal()
    try:
        rag = RAGService(db)
        result = await rag.query(user_id=1, query="FY24 Zomato financial report")
        
        print(f"\n{'='*60}")
        print(f"Answer: {result.answer[:200]}...")
        print(f"\nCitations: {len(result.sources)}")
        for i, src in enumerate(result.sources[:3], 1):
            print(f"  [{i}] {src.document_title} (Page {src.page_number})")
        print(f"{'='*60}\n")
        
        # Check for errors
        if "[SYSTEM: Response Retracted" in result.answer:
            print("❌ FAILED: Response was retracted")
        elif "authorized document (NONE)" in result.answer.lower():
            print("❌ FAILED: (NONE) document ID issue")
        elif len(result.sources) > 0:
            print("✅ SUCCESS: Found relevant information with citations")
        else:
            print("⚠️  No citations (may be valid if document truly missing)")
            
    except Exception as e:
        logger.exception("Test failed")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_query())

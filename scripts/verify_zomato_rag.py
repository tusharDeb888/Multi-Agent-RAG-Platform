import sys
import os
import asyncio
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.application.services.rag_service import RAGService
from app.core.database import SessionLocal
from app.application.api.chat import ChatRequest

async def verify():
    print("Initializing RAG Service...")
    db = SessionLocal()
    rag = RAGService(db)
    
    query = "FY24 Zomato financial report"
    print(f"\nQuerying: '{query}'...")
    
    try:
        # Use user_id=1 (Admin/Test)
        response_dict = await rag.query(user_id=1, query=query)
        # Wrap dict in RAGResponse if needed, or just print keys
        # The service returns Dict or RAGResponse? Type hint says Dict but code might return RAGResponse
        # Line 1203 returns RAGResponse via Semantic Cache
        # But normal flow returns dict at line 1223/1235
        # Let's handle both
        if hasattr(response_dict, 'answer'):
            response = response_dict
        else:
             from app.domain.rag_types import RAGResponse
             response = RAGResponse(**response_dict)
        
        print("\n--- RESPONSE ---")
        print(response.answer)
        print("----------------")
        
        print(f"\nSources: {len(response.sources)}")
        for i, src in enumerate(response.sources):
            print(f"[{i+1}] {src.document_title or 'Unknown'} (Page {src.page_number}) - Score: {src.similarity_score:.4f}")
            print(f"    Content: {src.content[:100]}...")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify())

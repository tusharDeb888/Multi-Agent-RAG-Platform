import sys
import os
import asyncio
import json
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.application.services.rag_service import RAGService
from app.core.database import SessionLocal

async def verify_stream():
    print("Initializing RAG Service...")
    db = SessionLocal()
    rag = RAGService(db)
    
    query = "FY24 Zomato financial report"
    print(f"\nStream Querying: '{query}'...")
    
    answer_acc = []
    
    try:
        # Use user_id=1 (Admin/Test)
        async for chunk in rag.stream_query(user_id=1, query=query):
            if chunk.startswith("data: "):
                data_str = chunk[6:].strip()
                if data_str == "[DONE]":
                    break
                
                try:
                    data = json.loads(data_str)
                    if "token" in data:
                        token = data["token"]
                        print(token, end="", flush=True)
                        answer_acc.append(token)
                    elif "status" in data:
                        print(f"\n[STATUS: {data['status']}]")
                except json.JSONDecodeError:
                    pass
                    
        full_answer = "".join(answer_acc)
        print("\n\n--- FULL STREAMED ANSWER ---")
        print(full_answer)
        print("----------------------------")
        
        if "No grounded information found" in full_answer and "MULTIPLE_FILES" in full_answer:
            print("\n❌ FAILURE: Refusal detected with MULTIPLE_FILES error.")
        elif "INR 13,545 crore" in full_answer or "Zomato" in full_answer:
            print("\n✅ SUCCESS: Correct grounded answer received via stream.")
        else:
            print("\n⚠️ WARNING: Answer received but content verification needed.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_stream())

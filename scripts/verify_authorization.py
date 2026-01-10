import sys
import os
import asyncio
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from app.application.services.rag_service import RAGService
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.domain.models import DocumentChunk, Document

async def verify_authorization():
    logger.info("Initializing RAG Service for Authorization Verification...")
    
    # Mock DB Session (Not needed for this test if we mock dependencies or use real read-only)
    # We'll use real components but mock the "Context" behavior for unit-testing the Claim Logic
    # OR we integration test with real queries.
    # Real query is better.
    
    from app.core.database import SessionLocal
    db = SessionLocal()
    rag = RAGService(db)
    
    # Test 1: Weak/Vague Query (Coverage Gate)
    # Query: "thing" or "stuff" -> Should fail Coverage Check
    print("\n" + "-"*30)
    print("Test 1: Weak Query (Expect Refusal due to Coverage)")
    try:
        result_1 = await rag.query(user_id=1, query="stuff in the file")
        print(f"Answer: {result_1['answer']}")
        if "No grounded information" in result_1['answer'] or not result_1['citations']:
            print("✅ Test 1 PASSED: Correctly refused vague query.")
        else:
            print("❌ Test 1 FAILED: Answered vague query (Coverage Check failed).")
    except Exception as e:
        print(f"❌ Test 1 ERROR: {e}")

    # Test 2: Multi-Doc Ambiguity (Dominant Document)
    # Finding a query that matches multiple docs is hard without knowing data.
    # We will trust the unit test logic we injected.
    # But let's try a broad query "safety" which likely appears in many docs.
    print("\n" + "-"*30)
    print("Test 2: Broad Query (Expect Single Dominant Document)")
    try:
        # We assume dataset has "Safety" in multiple files.
        result_2 = await rag.query(user_id=1, query="safety precautions")
        
        # Check if citations come from ONE document ID (mostly)
        doc_ids = {c['document_id'] for c in result_2['citations']}
        print(f"Cited Doc IDs: {doc_ids}")
        
        if len(doc_ids) <= 1:
            print("✅ Test 2 PASSED: Verified strictly single-document (or empty).")
        else:
             print(f"⚠️ Test 2 WARNING: Cited multiple documents {doc_ids}. Check if Intent was COMPARISON or fallback.")
    except Exception as e:
         print(f"❌ Test 2 ERROR: {e}")

    # Test 3: Stopword Query (Fix for "is and")
    print("\n" + "-"*30)
    print("Test 3: Stopword Query (is and) - Expect Refusal")
    try:
        result_3 = await rag.query(user_id=1, query="is and")
        print(f"Answer: {result_3['answer']}")
        if ("No grounded information" in result_3['answer'] or "No information found" in result_3['answer']) and not result_3['citations']:
             print("✅ Test 3 PASSED: Refused stopword query.")
        else:
             print("❌ Test 3 FAILED: Answered stopword query!")
    except Exception as e:
         print(f"❌ Test 3 ERROR: {e}")

    # Test 4: Hallucination Injection (Claim Validation)
    # We can't easily force the LLM to hallucinate on demand without a jailbreak.
    # So we will unit-test the `_validate_claims` method directly here.
    print("\n" + "-"*30)
    print("Test 4: Unit Test Claim Validation (Hallucination Removal)")
    
    # Mock Chunks
    mock_chunk = DocumentChunk(
        id=999,
        document_id=1,
        content="The server listens on port 8080. The database is on port 5432.",
        page_number=1,
        chunk_index=0
    )
    mock_chunk.document = Document(filename="config.txt")
    
    # Mock Answer with 1 True Claim and 1 False Claim
    # True: "Port is 8080 [[999]]."
    # False: "The admin password is 'admin' [[999]]." (Semantic fail - 'password' not in chunk)
    
    mock_answer = "The server listens on port 8080 [[999]]. The admin password is 'admin' [[999]]."
    
    cleaned_answer = rag._validate_claims(mock_answer, [mock_chunk])
    print(f"Original: {mock_answer}")
    print(f"Cleaned:  {cleaned_answer}")
    
    if "port 8080" in cleaned_answer and "password" not in cleaned_answer:
        print("✅ Test 3 PASSED: Hallucinated claim removed.")
    elif "password" in cleaned_answer:
        print("❌ Test 3 FAILED: Hallucination NOT removed.")
    else:
        print("❌ Test 3 FAILED: Over-aggressive removal (True claim lost).")

    print("\n" + "-"*30)
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(verify_authorization())

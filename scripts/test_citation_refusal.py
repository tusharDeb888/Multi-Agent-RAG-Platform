"""
Test Citation Suppression on Refusal.
Mocks LLM to return refusal message and verifies RAGService suppresses citations.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from app.application.services.rag_service import RAGService
from app.infrastructure.llm.base import BaseLLMAdapter, LLMResponse, LLMRequest

class MockRefusalLLM(BaseLLMAdapter):
    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="I cannot find the answer in the provided documents.",
            tokens_used=10,
            model_name="mock"
        )
        
    def stream(self, request: LLMRequest):
        yield "I cannot "
        yield "find the "
        yield "answer in the "
        yield "provided documents."

    def get_model_info(self): return {}
    def is_available(self): return True
    def cleanup(self): pass

class MockPoliteRefusalLLM(BaseLLMAdapter):
    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="I can see this is about Zomato. However, the provided context does not directly answer the question.",
            tokens_used=10,
            model_name="mock"
        )
    def stream(self, request: LLMRequest):
        yield "The provided context "
        yield "does not directly answer "
        yield "the question."
        
    def get_model_info(self): return {}
    def is_available(self): return True
    def cleanup(self): pass

async def test_refusal_suppression():
    print("Testing Citation Suppression...")
    
    # Mock Dependencies
    mock_db = MagicMock()
    mock_vector = MagicMock()
    mock_vector.search.return_value = [("1", 0.9)] 
    
    mock_chunk = MagicMock()
    mock_chunk.id = 1
    mock_chunk.document_id = 100
    mock_chunk.document.filename = "secret.pdf"
    mock_chunk.content = "Secret Data"
    mock_chunk.page_number = 1
    
    # helper
    async def run_test(llm_adapter, name):
        print(f"\n--- Testing {name} ---")
        rag_service = RAGService(db=mock_db, llm_adapter=llm_adapter, vector_store=mock_vector)
        rag_service._retrieve_context = AsyncMock(return_value={
            "final_chunks": [mock_chunk], "candidate_count": 1, "accessible_count": 1
        })
        rag_service._is_chitchat = MagicMock(return_value=False)
        rag_service.cache.get = MagicMock(return_value=None)
        rag_service.cache.set = MagicMock()
        
        # Standard
        res = await rag_service.query(1, "q")
        if res['citations'] == []: print("✅ Standard: Citations Suppressed")
        else: print(f"❌ Standard: LEAKED! {res['citations']}")
        
        # Streaming
        citations = None
        async for chunk in rag_service.stream_query(1, "q"):
            if "citations" in chunk:
                import json
                data = json.loads(chunk.replace("data: ", ""))
                if "citations" in data: citations = data["citations"]
        
        if citations == []: print("✅ Stream: Citations Suppressed")
        else: print(f"❌ Stream: LEAKED! {citations}")

    await run_test(MockRefusalLLM(), "Explicit Refusal")
    await run_test(MockPoliteRefusalLLM(), "Polite/Edge Case Refusal")

if __name__ == "__main__":
    asyncio.run(test_refusal_suppression())

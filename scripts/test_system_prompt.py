
import asyncio
from app.application.services.rag_service import RAGService
from app.infrastructure.llm.base import BaseLLMAdapter, LLMRequest, LLMResponse

class MockLLM(BaseLLMAdapter):
    def generate(self, request: LLMRequest) -> LLMResponse:
        print(f"--- Mock LLM Received Request ---")
        print(f"System Prompt Present: {request.system_prompt is not None}")
        if request.system_prompt:
            print(f"System Prompt Preview: {request.system_prompt[:50]}...")
        return LLMResponse(text="Mock response", tokens_used=10, model_name="mock")

    async def stream(self, request: LLMRequest):
        yield "Mock"

    def get_model_info(self): return {}
    def is_available(self): return True
    def cleanup(self): pass

async def verify():
    # Mock dependencies
    mock_llm = MockLLM()
    service = RAGService(db=None, llm_adapter=mock_llm)
    
    # Test Query
    print("\nTesting Query:")
    try:
        await service.query(user_id=1, query="test", top_k=1)
    except Exception as e:
        # Ignore errors from missing DB/Embeddings/Cache, we just want to see the LLM call
        pass

if __name__ == "__main__":
    asyncio.run(verify())

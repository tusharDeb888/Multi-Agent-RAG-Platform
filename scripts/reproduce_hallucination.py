
import sys
import os
import asyncio
from app.application.services.rag_service import RAGService
from app.infrastructure.llm.factory import LLMFactory

# Setup
sys.path.append(os.getcwd())
from app.core.database import SessionLocal

async def reproduce():
    db = SessionLocal()
    factory = LLMFactory()
    llm = factory.create_llm_adapter(provider="ollama") # or "mistral"
    
    # Needs dependencies: embedding service, vector store
    from app.application.api.deps import get_embedding_service, get_vector_store, get_rbac_service
    embed = get_embedding_service()
    vec = get_vector_store()
    rbac = get_rbac_service(db)
    
    service = RAGService(
        db=db,
        llm_adapter=llm,
        embedding_service=embed,
        vector_store=vec,
        rbac_service=rbac
    )
    
    query = "tell me about Ruben Ausman"
    print(f"--- Query: {query} ---")
    
    # We want to inspect what happens inside.
    # We can't easily hook inside, but we can verify Retrieval results first.
    
    print("1. Running Retrieval Check...")
    chunks = await service._retrieve_context(query, user=None, filters=None)
    print(f"Retrieved {len(chunks)} candidates.")
    for c in chunks:
        print(f" - [{c.score:.4f}] {c.content[:50]}...")
        
    print("\n2. Running Full Query...")
    response = await service.query(query, user=None)
    print("Response Answer:")
    print(response.answer)

if __name__ == "__main__":
    asyncio.run(reproduce())


import asyncio
import sys
import os

# Setup Path
sys.path.append(os.getcwd())

from app.application.services.rag_service import RAGService
from app.infrastructure.llm.factory import LLMFactory
from app.core.config import get_settings, LLMProvider
from app.application.api.deps import get_rag_service, get_db

# Fake User ID
USER_ID = 1

async def verify_fix():
    print("🚀 Verifying CPU Scheduling Fix...")
    
    # 1. Bootstrap Service
    try:
        # We need to manually construct dependencies or use the DI container if possible
        # For simplicity, we'll try to use the 'deps' helper but it requires FastAPI context usually.
        # So we will instantiate manually.
        
        from app.core.config import get_settings
        from app.infrastructure.embeddings.embedding_service import EmbeddingService
        from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
        from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever
        from app.infrastructure.search.reranker_service import RerankerService
        from app.application.services.rbac_service import RBACService
        from app.domain.repositories.chunk_repository import ChunkRepository
        from app.domain.repositories.document_repository import DocumentRepository
        from app.infrastructure.cache.cache_service import CacheService
        from app.application.services.semantic_cache_service import SemanticCacheService
        from app.core.database import SessionLocal
        
        settings = get_settings()
        db = SessionLocal()
        
        print(" -> Initializing Dependencies...")
        
        # Repos
        chunk_repo = ChunkRepository(db)
        doc_repo = DocumentRepository(db)
        
        # Services
        llm_factory = LLMFactory()
        await llm_factory.warmup()
        llm = llm_factory.create_llm_adapter() # Use Ollama (Configured via env)
        
        embed_service = EmbeddingService()
        vec_store = MilvusVectorStore()
        bm25 = SparseBM25Retriever()
        reranker = RerankerService()
        rbac = RBACService(db=db)
        cache = CacheService()
        # Injection Hook for deps
        from app.application.api import deps
        deps._embedding_service = embed_service
        
        sem_cache = SemanticCacheService()
        
        rag = RAGService(
            db=db,
            llm_adapter=llm,
            embedding_service=embed_service,
            vector_store=vec_store,
            rbac_service=rbac
        )
        
        query = "CPU Scheduling criteria"
        print(f" -> Sending Query: '{query}'")
        
        full_text = ""
        async for chunk in rag.stream_query(user_id=USER_ID, query=query):
            if "token" in chunk: # Parse the SSE format manually or strict? 
                # The stream_query yields "data: {json}\n\n"
                pass 
                
            print(chunk.strip())
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_fix())

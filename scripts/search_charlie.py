
import sys
import os
import asyncio

# Ensure project root is in path
sys.path.append(os.getcwd())

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.domain.repositories.chunk_repository import ChunkRepository

async def search_query(query: str):
    print(f"🔎 Searching for: '{query}'")
    
    # 1. Initialize Services
    settings = get_settings()
    embeddings = EmbeddingService()
    store = MilvusVectorStore(settings)
    
    # 2. Embed Query
    print("Generating embedding...")
    query_vector = await embeddings.embed_query(query)
    
    # 3. Search (Super Admin Mode - No filters)
    print("Querying Milvus...")
    # Returns List[Tuple[chunk_id, distance]]
    results = await store.search(
        query_vector=query_vector,
        top_k=5,
        filter_ids=None # Super Admin access
    )
    
    if not results:
        print("No results found in Vector Store.")
        return

    # 4. Fetch Content from DB
    chunk_ids = [r[0] for r in results]
    scores = {r[0]: r[1] for r in results}
    
    print(f"Found {len(chunk_ids)} hits. Fetching content from DB...")
    
    with SessionLocal() as db:
        chunk_repo = ChunkRepository(db)
        chunks = chunk_repo.get_by_ids(chunk_ids)
        
        # Sort by score (which roughly matches order of chunk_ids from search, but let's be safe)
        # Actually search results are already sorted by distance.
        # We just need to map back.
        
        chunk_map = {c.id: c for c in chunks}
        
        for i, (cid, distance) in enumerate(results):
            chunk = chunk_map.get(cid)
            if not chunk:
                print(f"--- Result {i+1} (Score: {distance:.4f}) ---")
                print("WARNING: Chunk found in Milvus but missing in DB!")
                continue
                
            print(f"--- Result {i+1} (Score: {distance:.4f}) ---")
            print(f"Document ID: {chunk.document_id}")
            print(f"Chunk ID: {chunk.id}")
            print(f"Content: {chunk.content[:200]}...")
            print("-" * 50)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        q = sys.argv[1]
    else:
        q = "tell me about Rachel"
    
    asyncio.run(search_query(q))

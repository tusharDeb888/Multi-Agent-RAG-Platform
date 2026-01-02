#!/usr/bin/env python3
"""
Comprehensive RAG Retrieval Debugger
Traces the full pipeline: Query -> Embedding -> Search -> Filter -> Rerank -> Context
"""
import sys
import os
import asyncio
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.application.services.rag_service import RAGService
from app.domain.models import Document, DocumentChunk, User

async def debug_query(query: str, user_id: int = 1):
    """Debug a specific query through the entire RAG pipeline."""
    db = SessionLocal()
    try:
        rag = RAGService(db=db)
        
        print("="*80)
        print(f"QUERY: {query}")
        print(f"USER ID: {user_id}")
        print("="*80)
        
        # Get user info
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            print(f"\nUser: {user.username}")
            print(f"Department: {user.department.name if user.department else 'None'}")
            roles = [r.role.name for r in user.roles]
            print(f"Roles: {roles}")
        
        # Get accessible chunk IDs
        print("\n--- Phase 1: RBAC Policy Evaluation ---")
        accessible_chunk_ids = rag.rbac.get_accessible_chunk_ids(user_id)
        
        if accessible_chunk_ids is None:
            print("✓ Super Admin - No Filter (Access All)")
            total_chunks = db.query(DocumentChunk).count()
            print(f"  Total chunks in system: {total_chunks}")
        else:
            print(f"✓ Accessible chunks: {len(accessible_chunk_ids)}")
            if len(accessible_chunk_ids) < 50:
                print(f"  IDs: {accessible_chunk_ids[:20]}{'...' if len(accessible_chunk_ids) > 20 else ''}")
        
        # Generate embedding
        print("\n--- Phase 2a: Query Embedding ---")
        query_embedding = rag.embeddings.embed_text(query)
        print(f"✓ Embedding dimension: {len(query_embedding)}")
        print(f"  Sample values: {query_embedding[:5]}")
        
        # Vector search
        print("\n--- Phase 2b: Vector Search (FAISS) ---")
        vector_results = rag.vector_store.search(
            query_vector=query_embedding,
            top_k=20,
            filter_ids=accessible_chunk_ids
        )
        print(f"✓ Vector results: {len(vector_results)}")
        if vector_results:
            print("  Top 5 results:")
            for rank, (chunk_id, score) in enumerate(vector_results[:5], 1):
                chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
                if chunk:
                    doc_name = chunk.document.filename if chunk.document else "Unknown"
                    print(f"    {rank}. Chunk {chunk_id} | Score: {score:.4f} | Doc: {doc_name}")
                    print(f"       Preview: {chunk.content[:100]}...")
        
        # BM25 search
        print("\n--- Phase 2c: Keyword Search (BM25) ---")
        if rag.bm25.is_fitted:
            bm25_results = rag.bm25.search(query, top_k=20)
            print(f"✓ BM25 results (pre-filter): {len(bm25_results)}")
            
            # Apply filter
            if accessible_chunk_ids is not None:
                allowed_set = set(accessible_chunk_ids)
                bm25_results = [r for r in bm25_results if int(r[0]) in allowed_set]
            print(f"✓ BM25 results (post-filter): {len(bm25_results)}")
            
            if bm25_results:
                print("  Top 5 results:")
                for rank, (chunk_id, score) in enumerate(bm25_results[:5], 1):
                    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == int(chunk_id)).first()
                    if chunk:
                        doc_name = chunk.document.filename if chunk.document else "Unknown"
                        print(f"    {rank}. Chunk {chunk_id} | Score: {score:.4f} | Doc: {doc_name}")
        else:
            print("⚠ BM25 not fitted - skipping")
        
        # Fusion
        print("\n--- Phase 3: Reciprocal Rank Fusion ---")
        combined_scores = {}
        k = 60
        for rank, (chunk_id, _) in enumerate(vector_results):
            combined_scores[chunk_id] = combined_scores.get(chunk_id, 0) + (1 / (k + rank + 1))
        for rank, (chunk_id, _) in enumerate(bm25_results if rag.bm25.is_fitted else []):
            cid = int(chunk_id)
            combined_scores[cid] = combined_scores.get(cid, 0) + (1 / (k + rank + 1))
        
        sorted_candidates = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        print(f"✓ Fused candidates: {len(sorted_candidates)}")
        
        if sorted_candidates:
            print("  Top 10:")
            for rank, (chunk_id, score) in enumerate(sorted_candidates[:10], 1):
                chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
                if chunk:
                    doc_name = chunk.document.filename if chunk.document else "Unknown"
                    print(f"    {rank}. Chunk {chunk_id} | RRF: {score:.6f} | Doc: {doc_name}")
        
        # Reranking
        print("\n--- Phase 4: Cross-Encoder Reranking ---")
        candidate_ids = [int(cid) for cid, _ in sorted_candidates[:20]]
        
        if candidate_ids:
            chunks = rag.chunk_repo.get_by_ids(candidate_ids)
            chunks_map = {c.id: c for c in chunks}
            rerank_chunk_docs = [chunks_map[cid] for cid in candidate_ids if cid in chunks_map]
            
            if rerank_chunk_docs:
                chunk_texts = [c.content for c in rerank_chunk_docs]
                ranked_results = rag.ranker.rank(query, chunk_texts, top_k=5)
                
                print(f"✓ Ranked {len(ranked_results)} chunks")
                print("  Results:")
                for idx, score in ranked_results:
                    chunk = rerank_chunk_docs[idx]
                    doc_name = chunk.document.filename if chunk.document else "Unknown"
                    print(f"    Chunk {chunk.id} | Score: {score:.4f} | Doc: {doc_name}")
                    print(f"    Content: {chunk.content[:150]}...")
                    print()
                
                # Check threshold
                print("\n--- Phase 5: Threshold Filtering ---")
                if ranked_results:
                    best_score = ranked_results[0][1]
                    print(f"Best score: {best_score:.4f}")
                    print(f"Absolute threshold: -5.0")
                    print(f"Relative threshold: {best_score - 4.0:.4f}")
                    
                    final_count = 0
                    for idx, score in ranked_results:
                        if score > -5.0 and score > (best_score - 4.0):
                            final_count += 1
                        else:
                            print(f"  ✗ Chunk {rerank_chunk_docs[idx].id} filtered (score: {score:.4f})")
                    
                    print(f"\n✓ Final chunks: {final_count}")
                    
                    if final_count == 0:
                        print("\n⚠️ NO CHUNKS PASSED RERANKER!")
                        print("Possible reasons:")
                        print("  1. Query semantically different from document content")
                        print("  2. Threshold too strict for this use case")
                        print("  3. Embeddings model mismatch")
                        print("  4. Content chunked poorly (broke entity boundaries)")
        
        print("\n" + "="*80)
        
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="The query to debug")
    parser.add_argument("--user", type=int, default=1, help="User ID (default: 1)")
    
    args = parser.parse_args()
    
    asyncio.run(debug_query(args.query, args.user))

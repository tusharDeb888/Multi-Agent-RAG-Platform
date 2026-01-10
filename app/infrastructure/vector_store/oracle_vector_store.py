"""
Oracle Vector Store implementation.
Requires Oracle Database 23c or later with Vector Search support.
Refactored to Async Interface with Bulk Operations.
"""
from typing import List, Tuple, Optional, Dict
import numpy as np
import json
import asyncio
from loguru import logger
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from app.infrastructure.vector_store.base import BaseVectorStore
from app.core.database import SessionLocal

class OracleVectorStore(BaseVectorStore):
    """
    Oracle-based vector store using Oracle Database 23c AI Vector Search.
    Wraps synchronous DB calls in asyncio.to_thread.
    """
    
    def __init__(self, dimension: int):
        """
        Initialize Oracle vector store.
        """
        self.dimension = dimension
        # We don't hold a persistent session here often to avoid thread affinity issues
        # with to_thread, but creating one per op is safer for async wrapper.
        
    async def add_vectors(self, vectors: np.ndarray, ids: List[int], metadata: Optional[List[dict]] = None) -> None:
        """
        Add vectors to Oracle database (Bulk Update).
        """
        if len(vectors) == 0 or not ids:
            return
            
        # Prepare data for Bulk Update
        data = []
        for i, chunk_id in enumerate(ids):
            # Oracle Vector Binding: typically string
            vector_list = vectors[i].tolist()
            vector_str = json.dumps(vector_list)
            data.append({
                "chunk_id": chunk_id,
                "vector_data": vector_str
            })
            
        stmt = text("""
            UPDATE document_chunks 
            SET vector_embedding = VECTOR(:vector_data)
            WHERE id = :chunk_id
        """)
        
        try:
             def _execute_bulk():
                 with SessionLocal() as db:
                     db.execute(stmt, data) # SQLAlchemy uses executemany for list of dicts
                     db.commit()
                     # logger.info(f"Updated {len(ids)} vectors in Oracle (Bulk)")

             await asyncio.to_thread(_execute_bulk)
             
        except Exception as e:
            logger.error(f"Error adding vectors to Oracle: {e}")
            raise

    async def search(self, query_vector: np.ndarray, top_k: int, filter_ids: Optional[List[int]] = None) -> List[Tuple[int, float]]:
        """
        Search for similar vectors using Oracle Vector Search.
        """
        vector_list = query_vector.tolist()
        vector_str = json.dumps(vector_list)
        
        # Base Query
        sql = """
            SELECT id, VECTOR_DISTANCE(vector_embedding, VECTOR(:query_vector)) as distance
            FROM document_chunks
            WHERE vector_embedding IS NOT NULL
        """
        
        params = {"query_vector": vector_str, "top_k": top_k}
        
        if filter_ids:
            # Safe binding for IN clause
            sql += " AND id IN :f_ids"
            
        sql += " ORDER BY distance ASC FETCH FIRST :top_k ROWS ONLY"
        
        stmt = text(sql)
        if filter_ids:
             stmt = stmt.bindparams(bindparam('f_ids', expanding=True))
             params["f_ids"] = filter_ids
             
        try:
             def _execute_search():
                 with SessionLocal() as db:
                     result = db.execute(stmt, params).fetchall()
                     return [(row[0], row[1]) for row in result] # id, distance

             raw_results = await asyncio.to_thread(_execute_search)
             
             matches = []
             for chunk_id, distance in raw_results:
                 # Convert distance to similarity
                 # If Cosine Distance (0..2), Sim = 1 - Dist/2 or just 1-Dist if normalized?
                 # Assuming standard Euclidean or Cosine distance behavior:
                 # Standard conversion for generic RAG ranking:
                 similarity = 1 / (1 + distance) 
                 matches.append((chunk_id, similarity))
                 
             return matches
             
        except Exception as e:
            logger.error(f"Error searching Oracle vectors: {e}")
            return []

    async def search_batch(self, query_vectors: np.ndarray, top_k: int, filter_ids: Optional[List[int]] = None) -> List[List[Tuple[int, float]]]:
        """
        Batch Search.
        Sequential execution for now, can be parallelized.
        """
        results = []
        for vec in query_vectors:
             res = await self.search(vec, top_k, filter_ids)
             results.append(res)
        return results

    async def delete_vectors(self, ids: List[int]) -> None:
        """Delete vectors (set to NULL)."""
        if not ids:
            return
            
        stmt = text("UPDATE document_chunks SET vector_embedding = NULL WHERE id IN :ids")
        stmt = stmt.bindparams(bindparam('ids', expanding=True))
        
        try:
             def _execute_delete():
                 with SessionLocal() as db:
                     db.execute(stmt, {"ids": ids})
                     db.commit()
                     
             await asyncio.to_thread(_execute_delete)
             
        except Exception as e:
            logger.error(f"Error deleting vectors from Oracle: {e}")
            raise

    async def get_vector(self, id: int) -> Optional[np.ndarray]:
        """Get vector stub."""
        return None

    async def save(self, path: str) -> None:
        pass
    
    async def load(self, path: str) -> None:
        pass
    
    async def cleanup(self) -> None:
        """Resources managed by context managers in methods."""
        pass

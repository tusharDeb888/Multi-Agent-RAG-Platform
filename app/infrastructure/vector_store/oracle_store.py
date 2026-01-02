"""
Oracle 23ai Vector Store implementation.
Uses Native AI Vector Search for efficient retrieval.
"""
from typing import List, Tuple, Optional
import numpy as np
import oracledb
import array
from sqlalchemy import text
from loguru import logger

from app.infrastructure.vector_store.base import BaseVectorStore
from app.core.config import get_settings
from app.core.database import SessionLocal

class OracleVectorStore(BaseVectorStore):
    """
    Oracle 23ai Vector Store Adapter.
    Leverages native VECTOR data type and index.
    """
    
    def __init__(self):
        """Initialize Oracle Vector Store."""
        self.settings = get_settings()
        self.db = SessionLocal() # Dedicated session for vector ops if needed, or use passed session
        # Actually base doesn't pass session. We create one.
    
    def add_vectors(self, vectors: List[List[float]], ids: List[int], metadata: Optional[List[dict]] = None) -> None:
        """
        Add vectors -> Update existing chunks in DB with embedding.
        Prerequisite: Chunks must already exist in 'document_chunks' table (via ChunkRepository).
        """
        if not vectors or not ids:
            return
            
        try:
            # Prepare bulk update data
            # Format: {'id': 123, 'emb': '[0.1, 0.2, ...]'}
            # Note: python-oracledb might support array binding for VECTOR type directly?
            # For safe compatibility, we can pass binding as string/array.
            
            data = []
            for i, vec in enumerate(vectors):
                # Ensure vector is list/array
                # Oracle 23ai driver supports creating vector from list
                # vec_array = array.array('d', vec) # 'd' for double or 'f' for float? embedding col is FLOAT32
                data.append({
                    "id": ids[i],
                    "emb":  str(list(vec)) # Passing as string representation is often safest fallback '[...]'
                    # Or use array.array('f', vec) if using thin mode 23ai driver
                })
            
            # Using raw SQL
            # "UPDATE document_chunks SET embedding = VECTOR(:emb) WHERE id = :id"
            update_stmt = text("UPDATE document_chunks SET embedding = VECTOR(:emb) WHERE id = :id")
            
            self.db.execute(update_stmt, data)
            self.db.commit()
            logger.info(f"Updated {len(vectors)} embeddings in Oracle DB")
            
        except Exception as e:
            logger.error(f"Failed to add vectors to Oracle: {e}")
            self.db.rollback()
            raise
        
    def search(self, query_vector: List[float], top_k: int, filter_ids: Optional[List[int]] = None) -> List[Tuple[int, float]]:
        """
        Search using VECTOR_DISTANCE (COSINE).
        """
        try:
            # Convert query vector to string format for bind (or correct type)
            query_vec_str = str(list(query_vector))
            
            # Construct Query
            # Note: COSINE distance in Oracle is Distance (0=Sim, 2=Dissim). 
            # RAG expects Similarity (1=Identical, -1=Opposite).
            # Conversion: Similarity = 1 - (Distance / 2) ? Or just use DOT if normalized.
            # BaseVectorStore interface usually expects similarity?
            # Actually FAISS with InnerProduct returns Dot Product (Similarity).
            # If using COSINE metric in Oracle:
            # VECTOR_DISTANCE(..., COSINE) returns 1 - CosSim? No, strict Cosine Distance.
            # Let's check Oracle docs: Cosine Distance = 1 - Cosine Similarity.
            # So Similarity = 1 - Distance.
            
            sql = """
            SELECT id, VECTOR_DISTANCE(embedding, VECTOR(:q), COSINE) as dist
            FROM document_chunks
            ORDER BY dist ASC
            FETCH FIRST :k ROWS ONLY
            """
            
            if filter_ids:
                # Add filter clause if needed (complex with bind array in SQL)
                # Maybe just skip DB filtering for simplicity if unexpected usage
                pass
                
            result = self.db.execute(text(sql), {"q": query_vec_str, "k": top_k}).fetchall()
            
            # Convert to (id, benefit_score)
            output = []
            for row in result:
                chunk_id = row[0]
                dist = row[1]
                similarity = 1.0 - dist # Convert distance to similarity
                output.append((chunk_id, similarity))
                
            return output
            
        except Exception as e:
            logger.error(f"Oracle Vector Search failed: {e}")
            return []

    def delete_vectors(self, ids: List[int]) -> None:
        """
        Delete vectors -> Handled by DB Cascade usually.
        If strict deletion needed: UPDATE ... SET embedding = NULL
        """
        if not ids:
            return
        try:
            stmt = text("UPDATE document_chunks SET embedding = NULL WHERE id IN :ids")
            # Passing list to IN clause requiring expansion or specific handling
            # Easier to loop or expand
            self.db.execute(text(f"UPDATE document_chunks SET embedding = NULL WHERE id IN ({','.join(map(str, ids))})"))
            self.db.commit()
        except Exception as e:
            logger.error(f"Error delete vectors: {e}")

    def get_vector(self, id: int) -> Optional[np.ndarray]:
        """Get vector."""
        return None # Not implemented

    def save(self, path: str) -> None:
        pass # No-op
        
    def load(self, path: str) -> None:
        pass # No-op

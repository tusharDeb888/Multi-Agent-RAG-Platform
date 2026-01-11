"""
Base interface for vector stores.
Follows Interface Segregation Principle.
Refactored to ASYNC interface for Non-Blocking I/O and Scalability.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
import numpy as np


class BaseVectorStore(ABC):
    """
    Abstract base class for vector stores.
    All I/O operations must be non-blocking (async).
    """
    
    @abstractmethod
    async def add_vectors(self, vectors: np.ndarray, ids: List[int], metadata: Optional[List[dict]] = None) -> None:
        """
        Add vectors to the store asynchronously.
        
        Args:
            vectors: Array of vectors to add (N, D)
            ids: List of IDs corresponding to vectors
            metadata: Optional metadata for each vector
        """
        pass
    
    @abstractmethod
    async def search(self, query_vector: np.ndarray, top_k: int, filter_ids: Optional[List[int]] = None, metadata_filter: Optional[dict] = None) -> List[Tuple[int, float]]:
        """
        Search for similar vectors asynchronously.
        
        Args:
            query_vector: Query vector (1, D) or (D,)
            top_k: Number of results to return
            filter_ids: Optional list of IDs to filter by
            
        Returns:
            List of tuples (id, similarity_score)
        """
    @abstractmethod
    async def search_exact_subset(self, query_vector: np.ndarray, allowed_ids: List[int], top_k: int) -> List[Tuple[int, float]]:
        """
        Search within a specific subset of Chunk IDs (Zero-Trust Exact Match).
        
        Args:
            query_vector: Query vector
            allowed_ids: List of allowable Chunk IDs (strict whitelist)
            top_k: Number of results
            
        Returns:
            List of (id, score) tuples
        """
        pass

    @abstractmethod
    async def search_batch(self, query_vectors: np.ndarray, top_k: int, filter_ids: Optional[List[int]] = None) -> List[List[Tuple[int, float]]]:
        """
        Batch search for multiple query vectors.
        Critical for Fusion and Multi-Query RAG.
        
        Args:
            query_vectors: Matrix of query vectors (N, D)
            top_k: Number of results per query
            filter_ids: Optional global filter (or TODO: per-query filter)
            
        Returns:
             List of result lists, one per query.
        """
        pass
    
    @abstractmethod
    async def delete_vectors(self, ids: List[int]) -> None:
        """
        Delete vectors by IDs asynchronously.
        
        Args:
            ids: List of IDs to delete
        """
        pass
    
    @abstractmethod
    async def get_vector(self, id: int) -> Optional[np.ndarray]:
        """
        Get a vector by ID asynchronously.
        
        Args:
            id: Vector ID
            
        Returns:
            Vector array or None if not found
        """
        pass
    
    @abstractmethod
    async def save(self, path: str) -> None:
        """Save the index to disk asynchronously."""
        pass
    
    @abstractmethod
    async def load(self, path: str) -> None:
        """Load the index from disk asynchronously."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources (close connections, free memory)."""
        pass

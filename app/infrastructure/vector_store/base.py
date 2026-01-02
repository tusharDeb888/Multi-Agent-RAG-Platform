"""
Base interface for vector stores.
Follows Interface Segregation Principle.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
import numpy as np


class BaseVectorStore(ABC):
    """
    Abstract base class for vector stores.
    Follows Dependency Inversion Principle.
    """
    
    @abstractmethod
    def add_vectors(self, vectors: np.ndarray, ids: List[int], metadata: Optional[List[dict]] = None) -> None:
        """
        Add vectors to the store.
        
        Args:
            vectors: Array of vectors to add
            ids: List of IDs corresponding to vectors
            metadata: Optional metadata for each vector
        """
        pass
    
    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int, filter_ids: Optional[List[int]] = None) -> List[Tuple[int, float]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filter_ids: Optional list of IDs to filter by
            
        Returns:
            List of tuples (id, similarity_score)
        """
        pass
    
    @abstractmethod
    def delete_vectors(self, ids: List[int]) -> None:
        """
        Delete vectors by IDs.
        
        Args:
            ids: List of IDs to delete
        """
        pass
    
    @abstractmethod
    def get_vector(self, id: int) -> Optional[np.ndarray]:
        """
        Get a vector by ID.
        
        Args:
            id: Vector ID
            
        Returns:
            Vector array or None if not found
        """
        pass
    
    @abstractmethod
    def save(self, path: str) -> None:
        """Save the index to disk."""
        pass
    
    @abstractmethod
    def load(self, path: str) -> None:
        """Load the index from disk."""
        pass





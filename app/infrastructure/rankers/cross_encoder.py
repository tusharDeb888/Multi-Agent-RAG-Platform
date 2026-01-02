"""
Cross Encoder Ranker.
Re-ranks documents using a cross-encoder model.
"""
from typing import List, Dict, Any, Tuple
from sentence_transformers import CrossEncoder
from loguru import logger

class CrossEncoderRanker:
    """
    Reranks documents using a cross-encoder.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CrossEncoderRanker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize cross encoder.
        
        Args:
            model_name: Name of the huggingface model
        """
        if self._initialized:
            return
            
        try:
            self.model = CrossEncoder(model_name)
            logger.info(f"Loaded CrossEncoder model: {model_name}")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to load CrossEncoder model {model_name}: {e}")
            self.model = None
            
    def rank(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[int, float]]:
        """
        Rank documents.
        
        Args:
            query: Query string
            documents: List of document texts
            top_k: Number of results to return
            
        Returns:
            List of (original_index, score) tuples, sorted by score descending
        """
        if not self.model or not documents:
            return []
            
        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs)
        
        # Enumerate to keep track of original indices
        scored_docs = list(enumerate(scores))
        
        # Sort by score descending
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        return scored_docs[:top_k]

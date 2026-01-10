"""
Embedding service for generating vector embeddings.
Follows Single Responsibility Principle - only handles embeddings.
"""
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer
from loguru import logger

from app.core.config import get_settings


class EmbeddingService:
    """
    Service for generating text embeddings.
    Uses SentenceTransformers for consistent, high-quality embeddings.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize embedding service."""
        if self._initialized:
            return
            
        self.settings = get_settings()
        self.model = None
        self._load_model()
        self._initialized = True
    
    def _load_model(self) -> None:
        """Load the embedding model with Device Acceleration."""
        try:
            import torch
            
            # Use a model that matches vector_dimension
            # For 384 dimensions, use all-MiniLM-L6-v2
            # For 768 dimensions, use all-mpnet-base-v2
            if self.settings.vector_dimension == 384:
                model_name = "sentence-transformers/all-MiniLM-L6-v2"
            elif self.settings.vector_dimension == 768:
                model_name = "sentence-transformers/all-mpnet-base-v2"
            else:
                # Default to 384
                model_name = "sentence-transformers/all-MiniLM-L6-v2"
                logger.warning(f"Using default model for dimension {self.settings.vector_dimension}")
            
            # Device Selection
            device = "cpu"
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
                
            logger.info(f"Loading embedding model: {model_name} on DEVICE={device}")
            self.model = SentenceTransformer(model_name, device=device)
            logger.info("Embedding model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text
            
        Returns:
            Numpy array of embeddings
        """
        if not self.model:
            raise RuntimeError("Embedding model not loaded")
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for a batch of texts.
        
        Args:
            texts: List of input texts
            batch_size: Batch size for processing
            
        Returns:
            Numpy array of embeddings (shape: [len(texts), vector_dimension])
        """
        if not self.model:
            raise RuntimeError("Embedding model not loaded")
        
        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=len(texts) > 100
            )
            return embeddings
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise
    
    def get_dimension(self) -> int:
        """Get the dimension of embeddings."""
        return self.settings.vector_dimension





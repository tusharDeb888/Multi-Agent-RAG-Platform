import asyncio
import torch
import gc
import threading
from typing import List, Dict, Any, Tuple, Optional
from sentence_transformers import CrossEncoder
from loguru import logger

class CrossEncoderRanker:
    """
    Reranks documents using a cross-encoder.
    Singleton pattern to load model once.
    Thread-safe and Async-io safe.
    """
    
    _instance = None
    _init_lock = threading.Lock() # Thread-safe lock for __new__
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super(CrossEncoderRanker, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize cross encoder structure.
        Model loading is deferred to warmup() or first rank() call.
        """
        if self._initialized:
            return
            
        self.model_name = model_name
        self.model = None
        self.device = self._select_device()
        self._async_lock = asyncio.Lock() # Async lock for lazy loading
        self._initialized = True
        logger.info(f"CrossEncoderRanker initialized (Lazy Load). Device: {self.device}")

    def _select_device(self) -> str:
        """Select best available device (MPS, CUDA, CPU)."""
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
             # Check for Generic M-series support
            return "mps"
        return "cpu"

    async def warmup(self):
        """
        Explicitly load the model asynchronously.
        Useful for startup hooks (lifespan).
        """
        if self.model is not None:
             return
             
        async with self._async_lock:
             if self.model is None:
                 await asyncio.to_thread(self._load_model_sync)

    def _load_model_sync(self):
        """Synchronous model loading (to be run in executor)."""
        try:
            logger.info(f"Loading CrossEncoder: {self.model_name} on {self.device}...")
            # Enforce max_length to prevent OOM on massive inputs
            self.model = CrossEncoder(self.model_name, device=self.device, max_length=512)
            logger.info("CrossEncoder loaded successfully.")
        except Exception as e:
            logger.critical(f"Failed to load CrossEncoder: {e}")
            self.model = None
            raise RuntimeError(f"CrossEncoder failed to load: {e}")

    async def rank(
        self, 
        query: str, 
        documents: List[str], 
        top_k: int = 5,
        batch_size: int = 32
    ) -> List[Tuple[int, float]]:
        """
        Rank documents asynchronously.
        Auto-loads model if not ready (Lazy Loading).
        """
        if not query or not query.strip():
            logger.warning("Empty query passed to ranker. Returning empty.")
            return []
            
        if not documents:
            return []
            
        # Lazy Loading
        if self.model is None:
            logger.info("Lazy loading CrossEncoder model...")
            await self.warmup()
            
        if self.model is None:
             logger.error("CrossEncoder model is None after warmup. System Failure.")
             return []
             
        try:
            # Prepare pairs
            pairs = [[query, doc] for doc in documents]
            
            # Run inference in thread executor
            # batch_size handles large lists efficiently
            scores = await asyncio.to_thread(
                self.model.predict, 
                pairs, 
                batch_size=batch_size, 
                show_progress_bar=False,
                convert_to_numpy=True
            )
            
            # Convert numpy scores to standard floats if needed, though zip handles it.
            # Enumerate to keep track of original indices
            scored_docs = []
            for idx, score in enumerate(scores):
                scored_docs.append((idx, float(score)))
            
            # Sort by score descending
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            return scored_docs[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}. Falling back to original order (Graceful Degradation).")
            # Fallback: Return original indices with neutral score to preserve retrieval results
            return [(i, 0.0) for i in range(len(documents))][:top_k]

    async def cleanup(self):
        """Release resources."""
        # Acquire lock to ensure we don't delete while loading
        async with self._async_lock:
            if self.model:
                del self.model
                self.model = None
                
        if self.device == "cuda":
            torch.cuda.empty_cache()
        elif self.device == "mps":
            torch.mps.empty_cache()
        gc.collect()
        logger.info("CrossEncoder resources released.")


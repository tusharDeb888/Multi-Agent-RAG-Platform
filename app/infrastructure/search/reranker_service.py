import logging
from typing import List, Tuple
from app.domain.models import DocumentChunk
from app.infrastructure.rankers.cross_encoder import CrossEncoderRanker
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class RerankerService:
    def __init__(self):
        """
        Initialize the Reranker Service.
        Delegates to the infrastructure CrossEncoderRanker.
        Uses settings for model selection to avoid hardcoding.
        """
        settings = get_settings()
        # Default fallback matches the CrossEncoder default if setting is missing/none
        # Prioritize 'cross_encoder_model' from settings
        model_name = getattr(settings, "cross_encoder_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        
        # Singleton will handle initialization logic (idempotent)
        self.ranker = CrossEncoderRanker(model_name=model_name)
        logger.info(f"RerankerService initialized. Model: {model_name}")

    async def rerank(self, query: str, chunks: List[DocumentChunk], top_k: int = 10) -> Tuple[List[DocumentChunk], List[float]]:
        """
        Rerank a list of DocumentChunks based on query relevance.
        Returns: (top_k_chunks, top_k_scores)
        """
        if not chunks:
            return [], []

        # Extract texts for ranking
        documents = [chunk.content for chunk in chunks]
        
        logger.debug(f"Reranking {len(documents)} chunks for query: '{query[:50]}...'")
        
        # Call Async Ranker
        # Returns List[Tuple[original_index, score]]
        # Graceful degradation is handled inside CrossEncoderRanker
        scored_results = await self.ranker.rank(query, documents, top_k=top_k)
        
        final_chunks = []
        final_scores = []
        
        for idx, score in scored_results:
            if idx < len(chunks):
                final_chunks.append(chunks[idx])
                final_scores.append(score)
        
        logger.debug(f"Reranking complete. Returned {len(final_chunks)} chunks.")
            
        return final_chunks, final_scores

    async def cleanup(self):
        """Delegate cleanup."""
        await self.ranker.cleanup()

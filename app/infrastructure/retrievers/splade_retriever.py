import os
import pickle
import joblib
from typing import List, Dict, Tuple, Optional, Set
from loguru import logger
from app.core.config import get_settings

class SpladeRetriever:
    """
    SPLADE Retriever using a Chunk-Centric Forward Index.
    
    Structure:
    - index: Dict[chunk_id, Dict[token_id, weight]]
    
    Principles:
    1. Chunk-Centric: Stored by chunk_id, allowing O(1) updates/deletes.
    2. RBAC-First: Search REQUIREs allowed_chunk_ids.
    3. Persistence: Local disk storage via joblib.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SpladeRetriever, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        self.settings = get_settings()
        self.index_path = self.settings.splade_index_path
        self.index: Dict[int, Dict[int, float]] = {}
        self.inverted_cache: Dict[int, Set[int]] = {} # TokenID -> Set[ChunkID]
        self.is_dirty = False
        
        self.load()
        self._initialized = True
        
    def _update_inverted_cache(self, chunk_id: int, vector: Dict[int, float], remove: bool = False):
        """Update the in-memory inverted cache."""
        if remove:
            # We don't know old tokens easily without looking up old vector. 
            # But 'remove' is called before 'index' update usually? 
            # Actually, standard remove pattern:
            pass # See remove method
            
        for token_id in vector.keys():
            if token_id not in self.inverted_cache:
                self.inverted_cache[token_id] = set()
            self.inverted_cache[token_id].add(chunk_id)

    def _remove_from_inverted_cache(self, chunk_id: int, vector: Dict[int, float]):
        for token_id in vector.keys():
            if token_id in self.inverted_cache:
                self.inverted_cache[token_id].discard(chunk_id)
                if not self.inverted_cache[token_id]:
                    del self.inverted_cache[token_id]

    def add(self, chunk_id: int, vector: Dict[int, float]):
        """Add or update a SPLADE vector for a chunk."""
        # Check if exists to clean cache
        if chunk_id in self.index:
            self._remove_from_inverted_cache(chunk_id, self.index[chunk_id])
            
        self.index[chunk_id] = vector
        self._update_inverted_cache(chunk_id, vector)
        self.is_dirty = True
        
    def remove(self, chunk_id: int):
        """Remove a chunk from the index."""
        if chunk_id in self.index:
            self._remove_from_inverted_cache(chunk_id, self.index[chunk_id])
            del self.index[chunk_id]
            self.is_dirty = True

    def save(self):
        """Persist index to disk."""
        if not self.is_dirty: return
        try:
            # Atomic write pattern
            temp_path = self.index_path + ".tmp"
            joblib.dump(self.index, temp_path, compress=3)
            os.replace(temp_path, self.index_path)
            self.is_dirty = False
            logger.info(f"Saved SPLADE index with {len(self.index)} chunks.")
        except Exception as e:
            logger.error(f"Failed to save SPLADE index: {e}")

    def load(self):
        """Load index from disk and rebuild cache."""
        if os.path.exists(self.index_path):
            try:
                self.index = joblib.load(self.index_path)
                logger.info(f"Loaded SPLADE index: {len(self.index)} chunks. Rebuilding Cache...")
                
                # Rebuild Cache
                self.inverted_cache = {}
                for cid, vec in self.index.items():
                    for tid in vec:
                        if tid not in self.inverted_cache: 
                            self.inverted_cache[tid] = set()
                        self.inverted_cache[tid].add(cid)
                        
                logger.info("SPLADE Cache Rebuilt.")
            except Exception as e:
                logger.error(f"Failed to load SPLADE index: {e}. Starting fresh.")
                self.index = {}
                self.inverted_cache = {}
        else:
            self.index = {}
            self.inverted_cache = {}

    def search(
        self, 
        query_vector: Dict[int, float], 
        top_k: int, 
        allowed_chunk_ids: List[int]
    ) -> List[Tuple[int, float]]:
        """
        Search allowed chunks using SPLADE dot product.
        Optimized with Inverted Cache interaction.
        """
        if not query_vector: return []
        if not allowed_chunk_ids: 
            # If explicit empty list, return empty
            # If we want to support None = All, we handle it here or caller?
            # RagService now passes list(keys) if None, so allowed_chunk_ids is never None usually.
            # But let's be safe.
             return []
            
        scores = []
        q_tokens = set(query_vector.keys())
        
        # 1. Candidate Selection via Inverted Cache
        # Candidates = Union(Cache[t] for t in q_tokens)
        candidates = set()
        for t in q_tokens:
            if t in self.inverted_cache:
                candidates.update(self.inverted_cache[t])
        
        if not candidates:
            return []
            
        # 2. RBAC Filter: Intersect Candidates with Allowed IDs
        # If allowed_chunk_ids is a List, convert to Set for O(1) check
        allowed_set = set(allowed_chunk_ids)
        search_space = candidates.intersection(allowed_set)
        
        if not search_space:
            return []
            
        # 3. Score
        for cid in search_space:
            doc_vec = self.index[cid] # Guaranteed to exist
            
            # Dot Product
            score = 0.0
            # Common tokens? We know at least one matches.
            # Efficient dot product for sparse vectors:
            # Iterate query tokens (usually smaller 50 vs doc 150?)
            # Or iterate intersection?
            
            # Intersection is safest matching logic
            # Explicitly loop Q
            for t, q_val in query_vector.items():
                if t in doc_vec:
                    score += q_val * doc_vec[t]
            
            if score > 0:
                scores.append((cid, score))
                
        # Sort desc
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def clear(self):
        self.index = {}
        self.inverted_cache = {}
        self.is_dirty = True
        self.save()

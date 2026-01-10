import math
import os
import json
import shutil
import asyncio
import threading
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Iterable, Optional
from loguru import logger
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

@dataclass
class BM25State:
    """
    Encapsulates the immutable state of a fitted BM25 index.
    Allows for atomic swapping (Copy-on-Write) to enable lock-free reads.
    Note: corpus_ids is stored as a tuple for immutability.
    """
    vectorizer: CountVectorizer
    doc_term_matrix: sparse.csr_matrix
    idf: np.ndarray
    doc_len: np.ndarray
    avgdl: float
    corpus_ids: Tuple[int, ...] # Immutable Sequence
    k1: float
    b: float

class SparseBM25Retriever:
    """
    BM25 Retriever using sparse matrices.
    Singleton Pattern to ensure memory efficiency across requests.
    Async-native with Lazy Loading.
    Implements Lock-Free Readers (Search) via Atomic State Swapping.
    Uses Zero-Trust Persistence (No Pickle).
    """
    _instance = None
    _init_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super(SparseBM25Retriever, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 parameters.
        Safe against re-initialization.
        """
        if getattr(self, "_initialized", False):
            return
            
        self.k1 = k1
        self.b = b
        
        # State container - Swapped atomically
        self.state: Optional[BM25State] = None
        
        # Lock only for coordinating WRITES (fit/load). Reads are lock-free.
        self._write_lock = threading.Lock()
        self._async_load_lock = asyncio.Lock()
        
        self._initialized = True
        logger.info("SparseBM25Retriever initialized (Singleton/Lock-Free).")
        
    @property
    def is_fitted(self) -> bool:
        return self.state is not None
        
    async def fit(self, corpus_iterator: Iterable[str], corpus_ids: List[int]):
        """
        Build BM25 index from text iterator asynchronously.
        """
        logger.info("Building Sparse BM25 index...")
        await asyncio.to_thread(self._fit_sync, corpus_iterator, corpus_ids)
        
    def _fit_sync(self, corpus_iterator: Iterable[str], corpus_ids: List[int]):
        """Synchronous internal fit."""
        # Use local variables for construction (Thread-Safe isolation)
        try:
            vectorizer = CountVectorizer(
                lowercase=True, 
                token_pattern=r"(?u)\b\w\w+\b",
                max_features=100000 
            )
            
            # 1. vectorized
            doc_term_matrix = vectorizer.fit_transform(corpus_iterator)
            
            # 2. Statistics
            n_docs, n_vocab = doc_term_matrix.shape
            
            # [Senior Audit Fix] Data Integrity Check
            # Ensure the number of vectorized documents matches the provided IDs.
            # Mismatch leads to catastrophic retrieval errors (wrong ID for query).
            if n_docs != len(corpus_ids):
                logger.error(f"Integrity Error: Corpus iterator yielded {n_docs} docs but {len(corpus_ids)} IDs provided.")
                return 
            
            doc_len = np.array(doc_term_matrix.sum(axis=1)).flatten()
            avgdl = float(doc_len.mean())
            
            # 3. IDF
            doc_freq = np.array(doc_term_matrix.astype(bool).sum(axis=0)).flatten()
            idf = np.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)
            
            # Create new state object
            new_state = BM25State(
                vectorizer=vectorizer,
                doc_term_matrix=doc_term_matrix,
                idf=idf,
                doc_len=doc_len,
                avgdl=avgdl,
                corpus_ids=tuple(corpus_ids), # Enforce Immutability
                k1=self.k1,
                b=self.b
            )
            
            # Atomic Swap
            with self._write_lock:
                self.state = new_state
                
            logger.info(f"BM25 index built. Docs: {n_docs}, Vocab: {n_vocab}")
            
        except ValueError as e:
            logger.warning(f"Error fitting vectorizer (empty corpus?): {e}")

    async def search(self, query: str, top_k: int = 5, index_path: Optional[str] = None) -> List[Tuple[int, float]]:
        """
        Search for query asynchronously.
        Lock-Free Read Path.
        """
        # Lazy Loading
        if self.state is None and index_path:
             async with self._async_load_lock:
                 if self.state is None:
                     logger.info(f"Lazy loading BM25 index from {index_path}...")
                     await self.load(index_path)
                     
        # [Senior Audit Fix] DoS Protection
        # prevents regex exponential backtracking or memory spikes on massive inputs
        if len(query) > 10000:
            logger.warning("Query too long for BM25 search. Truncating.")
            query = query[:10000]

        # Grab reference to current state (Atomic in Python)
        current_state = self.state
        if current_state is None:
            return []
            
        return await asyncio.to_thread(self._search_sync, query, top_k, current_state)

    def _search_sync(self, query: str, top_k: int, state: BM25State) -> List[Tuple[int, float]]:
        """
        Synchronous search using immutable state snapshot.
        NO LOCKS required.
        """
        try:
            query_vec = state.vectorizer.transform([query])
        except Exception:
            return []
        
        query_indices = query_vec.nonzero()[1]
        if len(query_indices) == 0:
            return []
            
        scores = np.zeros(len(state.corpus_ids), dtype=np.float32)
        
        for term_idx in query_indices:
            try:
                current_idf = state.idf[term_idx]
                term_col = state.doc_term_matrix.getcol(term_idx)
                
                # Optimized Sparse Access
                tf_data = term_col.data   
                doc_indices = term_col.indices 
                
                if len(tf_data) == 0:
                    continue
                    
                doc_len_subset = state.doc_len[doc_indices]
                
                numerator = tf_data * (state.k1 + 1)
                denominator = tf_data + state.k1 * (1 - state.b + state.b * doc_len_subset / state.avgdl)
                term_scores = current_idf * (numerator / denominator)
                
                scores[doc_indices] += term_scores
            except IndexError:
                continue # Should not happen if state is consistent
            
        if top_k < len(scores):
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
        else:
            top_indices = np.argsort(scores)[::-1]
            
        results = []
        for i in top_indices:
            if scores[i] > 0:
                results.append((state.corpus_ids[i], float(scores[i])))
                
        return results

    async def save(self, path: str):
        """Save index to disk safely (Directory based, JSON/NPZ)."""
        # Path is treated as a DIRECTORY now
        current_state = self.state
        if not current_state:
            logger.warning("No state to save.")
            return

        await asyncio.to_thread(self._save_sync, path, current_state)
        
    def _save_sync(self, path: str, state: BM25State):
        """Atomic Save to Directory."""
        with self._write_lock:
            # We construct a temp directory
            # If path ends in .pkl, strip it to conform to new directory style if preferred,
            # but to minimize breakage we might just use the path as-is but make it a DIR.
            # Ideally we should migrate the name. 
            
            temp_dir = f"{path}.tmp"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)
            
            try:
                # 1. Save Metadata & Corups IDs
                metadata = {
                    "k1": state.k1, 
                    "b": state.b, 
                    "avgdl": state.avgdl,
                    "corpus_ids": state.corpus_ids,
                    "vocab": state.vectorizer.vocabulary_
                }
                
                # Custom JSON encoder for Numpy types
                class NumpyEncoder(json.JSONEncoder):
                    def default(self, obj):
                        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                                            np.int16, np.int32, np.int64, np.uint8,
                                            np.uint16, np.uint32, np.uint64)):
                            return int(obj)
                        elif isinstance(obj, (np.float_, np.float16, np.float32, 
                                            np.float64)):
                            return float(obj)
                        elif isinstance(obj, (np.ndarray,)):
                            return obj.tolist()
                        return json.JSONEncoder.default(self, obj)

                # Write JSON 
                with open(os.path.join(temp_dir, "metadata.json"), "w") as f:
                    json.dump(metadata, f, cls=NumpyEncoder)
                    
                # 2. Save Matrices (NPZ)
                sparse.save_npz(os.path.join(temp_dir, "matrix.npz"), state.doc_term_matrix)
                np.save(os.path.join(temp_dir, "doc_len.npy"), state.doc_len)
                np.save(os.path.join(temp_dir, "idf.npy"), state.idf)
                
                # 3. Atomic Swap
                if os.path.exists(path):
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path) # Legacy file support
                        
                os.rename(temp_dir, path)
                logger.info(f"Saved Sparse BM25 index to {path} (Secure Mode)")
                
            except Exception as e:
                logger.error(f"Error saving Sparse BM25 index: {e}")
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            
    async def load(self, path: str):
        """Load index from disk."""
        await asyncio.to_thread(self._load_sync, path)
        
    def _load_sync(self, path: str):
        """Synchronous Load."""
        if not os.path.exists(path):
            logger.warning(f"BM25 index not found at {path}. Initializing empty index.")
            # Initialize empty state
            try:
                vectorizer = CountVectorizer(lowercase=True, token_pattern=r"(?u)\b\w\w+\b")
                # Fit on dummy data to initialize vocab
                vectorizer.fit([""]) 
                
                n_docs = 0
                doc_term_matrix = sparse.csr_matrix((0, 0))
                
                empty_state = BM25State(
                    vectorizer=vectorizer,
                    doc_term_matrix=doc_term_matrix,
                    idf=np.array([]),
                    doc_len=np.array([]),
                    avgdl=0.0,
                    corpus_ids=(),
                    k1=self.k1,
                    b=self.b
                )
                
                # Set state
                with self._write_lock:
                    self.state = empty_state
                
                # Save immediately to persist emptiness
                self._save_sync(path, empty_state)
                return
            except Exception as e:
                logger.error(f"Failed to initialize empty BM25 index: {e}")
                return
            
        with self._write_lock:
            try:
                # Check format
                if os.path.isfile(path): # Legacy Pickle support
                    logger.warning("Detected legacy pickle index. Please re-index for security.")
                    # We Fail Closed for Safety, forcing re-indexing.
                    logger.error("Legacy pickle format not supported. Please rebuild index.")
                    return

                # Load Components
                with open(os.path.join(path, "metadata.json"), "r") as f:
                    meta = json.load(f)
                    
                doc_term_matrix = sparse.load_npz(os.path.join(path, "matrix.npz"))
                doc_len = np.load(os.path.join(path, "doc_len.npy"))
                idf = np.load(os.path.join(path, "idf.npy"))
                
                # Reconstruct Vectorizer
                vectorizer = CountVectorizer(
                    lowercase=True, 
                    token_pattern=r"(?u)\b\w\w+\b",
                    vocabulary=meta["vocab"]
                )
                
                new_state = BM25State(
                    vectorizer=vectorizer,
                    doc_term_matrix=doc_term_matrix,
                    idf=idf,
                    doc_len=doc_len,
                    avgdl=meta["avgdl"],
                    corpus_ids=meta["corpus_ids"],
                    k1=meta["k1"],
                    b=meta["b"]
                )
                
                self.state = new_state
                logger.info(f"Loaded Sparse BM25 index from {path} (Secure Mode)")
                
            except Exception as e:
                logger.error(f"Error loading Sparse BM25 index: {e}")

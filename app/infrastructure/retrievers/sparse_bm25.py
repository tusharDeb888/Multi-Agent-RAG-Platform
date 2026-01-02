"""
Sparse BM25 Retriever.
Implements BM25 using scikit-learn's CountVectorizer and sparse matrix operations
for memory efficiency and production scalability.
"""
import math
import pickle
import os
import numpy as np
from typing import List, Tuple, Iterable, Any, Optional
from loguru import logger
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

class SparseBM25Retriever:
    """
    BM25 Retriever using sparse matrices.
    Memory efficient implementation suitable for large corpora.
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 parameters.
        
        Args:
            k1: BM25 k1 parameter (term frequency saturation)
            b: BM25 b parameter (length normalization)
        """
        self.k1 = k1
        self.b = b
        
        self.vectorizer = CountVectorizer(
            lowercase=True, 
            token_pattern=r"(?u)\b\w\w+\b",
            max_features=50000 # Limit vocabulary to prevent OOM on noisy text
        )
        self.doc_term_matrix = None # Sparse matrix (N_docs, N_vocab)
        self.idf = None # Array (N_vocab,)
        self.doc_len = None # Array (N_docs,)
        self.avgdl = 0.0
        self.corpus_ids = [] # List of IDs
        self.is_fitted = False
        
    def fit(self, corpus_iterator: Iterable[str], corpus_ids: List[int]):
        """
        Build BM25 index from text iterator.
        
        Args:
            corpus_iterator: Iterator yielding text documents
            corpus_ids: List of document IDs corresponding to the iterator
        """
        logger.info("Building Sparse BM25 index...")
        
        # 1. vectorized: Compute Term Frequency (TF) sparse matrix
        # This will consume the iterator
        try:
            self.doc_term_matrix = self.vectorizer.fit_transform(corpus_iterator)
        except ValueError as e:
            logger.warning(f"Error fitting vectorizer (empty corpus?): {e}")
            self.is_fitted = False
            return

        self.corpus_ids = corpus_ids
        
        # 2. Compute Document Statistics
        n_docs, n_vocab = self.doc_term_matrix.shape
        self.doc_len = np.array(self.doc_term_matrix.sum(axis=1)).flatten()
        self.avgdl = self.doc_len.mean()
        
        # 3. Compute IDF
        # IDF(q) = log( (N - n(q) + 0.5) / (n(q) + 0.5) + 1 )
        # n(q) is doc frequency for term q
        
        # binarize to count docs containing term
        doc_freq = np.array(self.doc_term_matrix.astype(bool).sum(axis=0)).flatten()
        
        self.idf = np.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)
        
        self.is_fitted = True
        logger.info(f"BM25 index built. Docs: {n_docs}, Vocab: {n_vocab}")
        
    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """
        Search for query.
        
        Args:
            query: Query string
            top_k: Number of results
            
        Returns:
            List of (chunk_id, score) tuples
        """
        if not self.is_fitted:
            logger.warning("BM25 index not fitted")
            return []
            
        # 1. Transform query to sparse vector
        # (1, N_vocab)
        query_vec = self.vectorizer.transform([query])
        
        # Optimization: Only compute scores for docs that have query terms
        # But for simplicity and vectorized speed, we can compute for all implementation details
        # For very large index, we might want Inverted Index logic, but sparse dot product is fast.
        
        # BM25 Score formula:
        # score = sum( IDF * (TF * (k1 + 1)) / (TF + k1 * (1 - b + b * D/avgdl)) )
        
        # We process term by term efficiently using sparse operations only on query terms
        
        query_indices = query_vec.nonzero()[1]
        if len(query_indices) == 0:
            return []
            
        scores = np.zeros(len(self.corpus_ids))
        
        # Iterate over query terms (usually few)
        for term_idx in query_indices:
            # get column for this term -> (N_docs, 1) sparse
            term_col = self.doc_term_matrix.getcol(term_idx) 
            
            # Extract dense array for non-zero docs (efficient)
            # Or just operate on sparse
            
            # We need TF for this term for all docs
            tf = term_col.toarray().flatten()
            
            # Non-zero docs
            nz_mask = tf > 0
            if not np.any(nz_mask):
                continue
                
            tf_subset = tf[nz_mask]
            doc_len_subset = self.doc_len[nz_mask]
            
            # BM25 component for this term
            # component = IDF * (TF * (k1 + 1)) / (TF + k1 * (1 - b + b * len/avgdl))
            
            numerator = tf_subset * (self.k1 + 1)
            denominator = tf_subset + self.k1 * (1 - self.b + self.b * doc_len_subset / self.avgdl)
            
            term_score = self.idf[term_idx] * (numerator / denominator)
            
            scores[nz_mask] += term_score
            
        # Get top_k
        # Use argpartition for efficiency if k << N
        if top_k < len(scores):
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            # separate sort
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
        else:
            top_indices = np.argsort(scores)[::-1]
            
        results = []
        for i in top_indices:
            if scores[i] > 0:
                results.append((self.corpus_ids[i], float(scores[i])))
                
        return results

    def save(self, path: str):
        """Save index to disk."""
        try:
            with open(path, 'wb') as f:
                pickle.dump({
                    'vectorizer': self.vectorizer,
                    'doc_term_matrix': self.doc_term_matrix,
                    'idf': self.idf,
                    'doc_len': self.doc_len,
                    'avgdl': self.avgdl,
                    'corpus_ids': self.corpus_ids,
                    'is_fitted': self.is_fitted
                }, f)
            logger.info(f"Saved Sparse BM25 index to {path}")
        except Exception as e:
            logger.error(f"Error saving Sparse BM25 index: {e}")
            
    def load(self, path: str):
        """Load index from disk."""
        try:
            if not os.path.exists(path):
                logger.warning(f"BM25 index not found at {path}")
                return
                
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.vectorizer = data['vectorizer']
                self.doc_term_matrix = data['doc_term_matrix']
                self.idf = data['idf']
                self.doc_len = data['doc_len']
                self.avgdl = data['avgdl']
                self.corpus_ids = data['corpus_ids']
                self.is_fitted = data['is_fitted']
            logger.info(f"Loaded Sparse BM25 index from {path}")
        except Exception as e:
            logger.error(f"Error loading Sparse BM25 index: {e}")

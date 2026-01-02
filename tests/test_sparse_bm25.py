
import os
import shutil
import pytest
import numpy as np
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever

def test_sparse_bm25_workflow():
    """Test full workflow of SparseBM25Retriever."""
    
    # 1. Setup Data
    corpus = [
        "The quick brown fox jumps over the lazy dog",
        "The quick brown fox",
        "The lazy dog sleeps",
        "The quick rabbit jumps",
        "Random text about nothing relevant"
    ]
    ids = [1, 2, 3, 4, 5]
    
    # 2. Initialize and Fit
    retriever = SparseBM25Retriever(k1=1.5, b=0.75)
    
    # Use an iterator to simulate streaming
    def corpus_iter():
        for text in corpus:
            yield text
            
    retriever.fit(corpus_iter(), ids)
    
    assert retriever.is_fitted
    assert retriever.doc_term_matrix.shape[0] == 5
    assert len(retriever.corpus_ids) == 5
    
    # 3. Search
    # Query: "quick fox" -> Should match 1 and 2 strongly
    results = retriever.search("quick fox", top_k=3)
    
    print(f"\nResults for 'quick fox': {results}")
    
    assert len(results) > 0
    # Doc 1 and 2 should be top results
    top_ids = [r[0] for r in results]
    assert 2 in top_ids or 1 in top_ids
    
    # Query: "lazy" -> Should match 1 and 3
    results_lazy = retriever.search("lazy", top_k=2)
    print(f"Results for 'lazy': {results_lazy}")
    top_ids_lazy = [r[0] for r in results_lazy]
    assert 3 in top_ids_lazy or 1 in top_ids_lazy
    
    # 4. Save and Load
    test_path = "test_bm25_index.pkl"
    retriever.save(test_path)
    
    assert os.path.exists(test_path)
    
    # Load into new instance
    new_retriever = SparseBM25Retriever()
    new_retriever.load(test_path)
    
    assert new_retriever.is_fitted
    assert len(new_retriever.corpus_ids) == 5
    
    # Verify search result consistency
    results_loaded = new_retriever.search("quick fox", top_k=3)
    assert results_loaded == results
    
    # Cleanup
    os.remove(test_path)
    print("Test passed!")

if __name__ == "__main__":
    test_sparse_bm25_workflow()

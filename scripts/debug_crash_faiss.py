
import sys
import os
import logging
import numpy as np
import faiss
from datetime import datetime

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app to path
sys.path.append(os.getcwd())

# Fix for macOS OpenMP conflict
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from app.core.config import get_settings

def debug_faiss_crash():
    logger.info("Starting FAISS Crash Debug Script")
    settings = get_settings()
    
    dimension = settings.vector_dimension
    index_path = f"{settings.faiss_index_path}.index"
    
    logger.info(f"Dimension: {dimension}")
    logger.info(f"Index Path: {index_path}")
    
    try:
        # 1. Load or Create Index
        if os.path.exists(index_path):
            logger.info("Loading existing index...")
            index = faiss.read_index(index_path)
        else:
            logger.info("Creating new HNSW index (matching app)...")
            hnsw_index = faiss.IndexHNSWFlat(dimension, 32)
            index = faiss.IndexIDMap(hnsw_index)
            
        logger.info(f"Index size before: {index.ntotal}")
        
        # 2. Generate Dummy Data
        num_vectors = 103 # Same as the crash log
        logger.info(f"Generating {num_vectors} random vectors...")
        embeddings = np.random.rand(num_vectors, dimension).astype('float32')
        ids = np.arange(num_vectors).astype('int64') # FAISS might need int64 for IDMap
        
        # Note: IndexFlatL2 doesn't support add_with_ids directly unless wrapped in IndexIDMap
        # But our FAISSVectorStore wrapper handles this details. 
        # Let's check how FAISSVectorStore does it.
        # But for raw faiss test:
        
        logger.info("Adding vectors to FAISS index...")
        t0 = datetime.utcnow()
        
        # Check if index wraps an IDMap
        if isinstance(index, faiss.IndexIDMap):
            logger.info("Index is Map-based, using add_with_ids")
            index.add_with_ids(embeddings, ids)
        else:
            logger.info("Index is Flat, using add (IDs ignored)")
            index.add(embeddings)
        
        duration = (datetime.utcnow() - t0).total_seconds()
        logger.info(f"Addition completed in {duration:.2f}s")
        logger.info(f"Index size after: {index.ntotal}")
        
        # 3. Save
        logger.info("Saving index...")
        faiss.write_index(index, "test_debug.index")
        logger.info("Saved to test_debug.index")
        
        # Cleanup
        if os.path.exists("test_debug.index"):
            os.remove("test_debug.index")
            
        logger.info("SUCCESS: Did not crash.")
        
    except Exception as e:
        logger.error(f"CRASHED/FAILED: {e}", exc_info=True)

if __name__ == "__main__":
    # Simulate the fix BEFORE importing things if needed, 
    # but here we test if it crashes WITHOUT the fix first.
    debug_faiss_crash()

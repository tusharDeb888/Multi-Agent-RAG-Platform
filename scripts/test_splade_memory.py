import sys
import os
import torch
import time
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.infrastructure.embeddings.splade_service import SpladeService
from loguru import logger

def test_splade_memory():
    print("Initializing SPLADE...")
    svc = SpladeService()
    
    # Simulate a large batch that would previously crash 
    # (32 was crashing, let's try 40)
    batch_size = 40
    print(f"Generating input batch of {batch_size} long texts...")
    
    # Generate reasonably long fake text to stress memory
    # 500 words ~ 600-700 tokens (will be truncated to 512)
    sample_text = "The quick brown fox jumps over the lazy dog. " * 50
    texts = [f"Doc {i}: {sample_text}" for i in range(batch_size)]
    
    print("Starting Encode Batch...")
    t0 = time.time()
    
    try:
        results = svc.encode_batch(texts)
        dt = time.time() - t0
        
        print(f"\n✅ Success! Processed {len(results)} docs in {dt:.2f}s")
        print(f"Result count match: {len(results) == batch_size}")
        if results:
            print(f"Sample Vec Size: {len(results[0])} non-zero terms")
            
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if torch.backends.mps.is_available():
        print("Using MPS backend.")
    else:
        print("Using CPU (Test might be slow but valid for logic).")
        
    test_splade_memory()

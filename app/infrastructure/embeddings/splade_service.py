import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer
from typing import Dict, List
import numpy as np
from loguru import logger
from app.core.config import get_settings

class SpladeService:
    """
    SPLADE: Sparse Lexical and Expansion Model.
    Generates sparse vectors (Token ID -> Weight) for retrieval.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SpladeService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        self.settings = get_settings()
        self.model_name = self.settings.splade_model_name
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        
        logger.info(f"Loading SPLADE model: {self.model_name} on {self.device}...")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForMaskedLM.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            self._initialized = True
            logger.info("SPLADE model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load SPLADE model: {e}")
            raise
            
    def encode(self, text: str) -> Dict[int, float]:
        """
        Encode text into a sparse vector using SPLADE.
        Returns: Dict[token_id, weight]
        """
        if not text: return {}
        
        with torch.no_grad():
            inputs = self.tokenizer(
                text, 
                return_tensors="pt", 
                padding=True, 
                truncation=True, 
                max_length=512
            ).to(self.device)
            
            output = self.model(**inputs)
            logits = output.logits
            
            # SPLADE formula: log(1 + ReLU(logits))
            # We then take max across the sequence dimension (0)
            # shape: (batch_size, seq_len, vocab_size) -> (1, seq_len, vocab_size)
            
            # relu
            relu_log = torch.log(1 + torch.relu(logits))
            
            # Max pooling over sequence dimension (dim=1)
            # shape: (batch, vocab_size)
            values, _ = torch.max(relu_log, dim=1)
            
            # To sparse dict
            # We only care about non-zero elements
            # Apply a small threshold to cut noise? standard SPLADE keeps all > 0
            
            vector = values[0] # batch size 1
            
            # Get non-zero indices
            indices = torch.nonzero(vector).squeeze()
            if indices.dim() == 0: indices = indices.unsqueeze(0)
            
            sparse_dict = {}
            for idx in indices:
                val = vector[idx].item()
                if val > 0:
                    sparse_dict[int(idx)] = float(val)
                    
            return sparse_dict

    def encode_batch(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Encode a batch of texts effectively using vectorization with micro-batching to prevent OOM.
        """
        if not texts: return []
        
        # [Memory Fix] Micro-batch size for MPS - PERMANENT FIX
        # 32 is too large for full SPLADE logits (2GB+). 
        # Even 4 might be risky on 8GB machines with other apps open.
        # We set this to 2 to be ultra-conservative (~125MB peak).
        MICRO_BATCH_SIZE = 2
        
        all_results = []
        
        for i in range(0, len(texts), MICRO_BATCH_SIZE):
            batch_texts = texts[i : i + MICRO_BATCH_SIZE]
            
            try:
                with torch.no_grad():
                    inputs = self.tokenizer(
                        batch_texts, 
                        return_tensors="pt", 
                        padding=True, 
                        truncation=True, 
                        max_length=512
                    ).to(self.device)
                    
                    output = self.model(**inputs)
                    logits = output.logits # (MicroBatch, Seq, Vocab)
                    
                    # SPLADE: log(1 + ReLU(logits))
                    relu_log = torch.log(1 + torch.relu(logits))
                    
                    # Max pooling over sequence (dim=1) -> (MicroBatch, Vocab)
                    values, _ = torch.max(relu_log, dim=1)
                    
                    # Process current micro-batch results
                    for j in range(values.size(0)):
                        vec = values[j]
                        indices = torch.nonzero(vec).squeeze()
                        
                        if indices.dim() == 0 and indices.nelement() == 0:
                             all_results.append({})
                             continue
                        if indices.dim() == 0: indices = indices.unsqueeze(0)
                        
                        sparse_dict = {}
                        for idx in indices:
                            val = vec[idx].item()
                            if val > 0:
                                sparse_dict[int(idx)] = float(val)
                        all_results.append(sparse_dict)
                        
                    # Explicit cleanup for MPS
                    del inputs, output, logits, relu_log, values
                    if self.device == "mps":
                        torch.cuda.empty_cache() if torch.cuda.is_available() else torch.mps.empty_cache()
                        
            except RuntimeError as e:
                # Fallback or Log
                if "out of memory" in str(e).lower():
                    logger.error(f"SPLADE OOM on micro-batch {i}. Skipping this chunk to prevent crash.")
                    # Padding with empty results to maintain index alignment
                    all_results.extend([{} for _ in batch_texts])
                    torch.mps.empty_cache()
                else:
                    raise e
                    
        return all_results

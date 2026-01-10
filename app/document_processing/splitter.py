"""
Text Splitter.
Splits text into chunks using semantic sentence boundaries.
"""
from typing import List, Optional
import re

class RecursiveCharacterTextSplitter:
    """
    Splits text recursively by trying separators in order.
    Legacy support.
    """
    def __init__(
        self,
        separators: Optional[List[str]] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        length_function: callable = len
    ):
        self.separators = separators or ["\n\n", "\n", ".", " ", ""]
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        
    def split_text(self, text: str) -> List[str]:
        """
        [Fix] Delegate to SemanticSplitter for better chunking quality.
        Legacy method preserved for backward compatibility.
        """
        semantic_splitter = SemanticSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        return semantic_splitter.split_text(text)

class SemanticSplitter:
    """
    Splits text by preserving sentence boundaries.
    Uses regex to identify sentences and groups them into chunks.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 50
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        
    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using robust regex.
        Handles commonly abbreviated titles (Mr., Dr., etc.)
        """
        # Regex breakdown:
        # (?<!\w\.\w.) - Negative lookbehind for E.g.
        # (?<![A-Z][a-z]\.) - Negative lookbehind for titles like Mr.
        # (?<=\.|\?|\!) - Positive lookbehind for sentence enders
        # \s+ - whitespace
        # (?=[A-Z]) - Positive lookahead for capital letter
        
        # Simplified robust pattern (covers most cases)
        split_pattern = r'(?<!\b(?:Mr|Ms|Dr|Sr|Jr|vs|ex)\.)(?<!\bMrs\.)(?<!\bProf\.)(?<=\.|\?|\!)\s+(?=[A-Z0-9])'
        
        # Split and keep standard structure
        sentences = re.split(split_pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def split_text(self, text: str) -> List[str]:
        """
        Segment text into semantic chunks.
        """
        sentences = self._split_sentences(text)
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sent_len = len(sentence)
            
            # If a single sentence is bigger than chunk_size, we MUST hard split it
            if sent_len > self.chunk_size:
                # Flush current
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                
                # [Fix] Guard against infinite loop if chunk_size <= chunk_overlap
                step = max(1, self.chunk_size - self.chunk_overlap)
                for i in range(0, sent_len, step):
                    chunks.append(sentence[i : i + self.chunk_size])
                continue

            # Check if adding this sentence exceeds chunk size
            if current_length + sent_len + 1 > self.chunk_size:
                # Finish current chunk
                chunk_text = " ".join(current_chunk)
                chunks.append(chunk_text)
                
                # Handle Overlap: Keep sentences from end of current_chunk
                # that fit within overlap size
                overlap_buffer = []
                overlap_len = 0
                for s in reversed(current_chunk):
                    if overlap_len + len(s) < self.chunk_overlap:
                        overlap_buffer.insert(0, s)
                        overlap_len += len(s) + 1
                    else:
                        break
                
                current_chunk = list(overlap_buffer)
                current_length = overlap_len
            
            current_chunk.append(sentence)
            current_length += sent_len + 1 # +1 for space
            
        # Final flush
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        # [Fix] Filter out chunks smaller than min_chunk_size
        return [c for c in chunks if len(c) >= self.min_chunk_size]

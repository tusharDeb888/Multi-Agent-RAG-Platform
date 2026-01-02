"""
Text Splitter.
Splits text into chunks recursively using separators.
"""
from typing import List, Optional

class RecursiveCharacterTextSplitter:
    """
    Splits text recursively by trying separators in order.
    Inspired by LangChain's RecursiveCharacterTextSplitter.
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
        Split text into chunks.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        final_chunks = []
        
        # Get appropriate separator
        separator = self.separators[-1]
        for s in self.separators:
            if s == "":
                separator = s
                break
            if s in text:
                separator = s
                break
                
        # Split
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text) # Split by character
            
        # Merge splits
        info_splits = []
        current_chunk = []
        current_length = 0
        
        for split in splits:
            split_len = self.length_function(split)
            
            # If a single split is too large, recurse on it (unless we are at innermost separator)
            if split_len > self.chunk_size:
                    # Flush current chunk before adding recursion results
                    if current_chunk:
                        doc = separator.join(current_chunk)
                        if doc.strip():
                            final_chunks.append(doc)
                        current_chunk = []
                        current_length = 0
                    
                    # Recurse
                    next_separators = self.separators[self.separators.index(separator) + 1:]
                    recursive_splitter = RecursiveCharacterTextSplitter(
                        separators=next_separators,
                        chunk_size=self.chunk_size,
                        chunk_overlap=self.chunk_overlap,
                        length_function=self.length_function
                    )
                    sub_splits = recursive_splitter.split_text(split)
                    final_chunks.extend(sub_splits)
                    continue
            
            # Add separator back if needed (except for empty separator)
            if separator and len(info_splits) > 0: # Not the first one
                 # This logic is simplified; LangChain handles "keep_separator" more robustly
                 pass 

            if current_length + split_len + (len(separator) if current_chunk else 0) > self.chunk_size:
                # Chunk is full
                if current_chunk:
                    doc = separator.join(current_chunk)
                    if doc.strip():
                        final_chunks.append(doc)
                    
                    # Handle overlap 
                    # Simplification: keep last few items that fit in overlap
                    # For strict correctness, we'd need deque logic.
                    # Here we incorrectly just start new. 
                    # Fixing overlap logic:
                    
                    overlap_chunk = []
                    overlap_len = 0
                    # Walk backwards
                    for i in range(len(current_chunk) - 1, -1, -1):
                        item = current_chunk[i]
                        item_len = self.length_function(item)
                        if overlap_len + item_len < self.chunk_overlap:
                            overlap_chunk.insert(0, item)
                            overlap_len += item_len + len(separator)
                        else:
                            break
                            
                    current_chunk = overlap_chunk
                    current_length = overlap_len
            
            current_chunk.append(split)
            current_length += split_len + (len(separator) if len(current_chunk) > 1 else 0)
            
        if current_chunk:
            doc = separator.join(current_chunk)
            if doc.strip():
                final_chunks.append(doc)
                
        return final_chunks

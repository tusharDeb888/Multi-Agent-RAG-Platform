import sys
import os
import asyncio
from loguru import logger
from app.application.services.rag_service import RAGService
from app.domain.models import DocumentChunk, Document

# Adding project root
sys.path.append(os.getcwd())

async def reproduce_issue():
    print("reproducing synonym failure...")
    
    rag = RAGService(None) # Mock DB
    
    # 1. Test Key Extraction with Stemming/Plurals
    query = "Managing projects efficiently"
    terms = rag._extract_key_terms(query)
    print(f"Query: '{query}'")
    print(f"Extracted Terms: {terms}")
    # Expect: {'managing', 'projects', 'efficiently'}
    
    # Mock Chunk: "Project Management efficiency is key."
    # Terms: {'project', 'management', 'efficiency', 'key'}
    chunk_text = "Project Management efficiency is key."
    chunk_terms = rag._extract_key_terms(chunk_text)
    print(f"Chunk Text: '{chunk_text}'")
    print(f"Chunk Terms: {chunk_terms}")
    
    # Intersection
    overlap = terms.intersection(chunk_terms)
    print(f"Overlap: {overlap}")
    
    if not overlap:
        print("❌ FAILURE REPRODUCED: No overlap found despite semantic match.")
    else:
        print("✅ No failure: Overlap found.")

if __name__ == "__main__":
    asyncio.run(reproduce_issue())


import asyncio
import os
import sys

from sqlalchemy import text # Correct placement

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever
from app.application.services.ingestion_service import IngestionService
from app.application.services.vision_service import VisionService
from loguru import logger

# Config Logger
logger.remove()
logger.add(sys.stderr, level="INFO")

async def full_reindex():
    print("⚠️  STARTING FULL RE-INDEX (DEEP CLEAN) ⚠️")
    print("This will WIPE the Vector Store and re-ingest all valid documents using Vision OCR.")
    
    db = SessionLocal()
    try:
        # 1. Purge Vector Store
        store = MilvusVectorStore()
        print(f"Dropping collection '{store.collection_name}'...")
        store.client.drop_collection(store.collection_name)
        # Re-create (Ensure Schema)
        store._ensure_collection_sync()
        print("✅ Vector Store Purged. All ghosts are gone.")
        
        # 2. Get Valid Documents
        docs = db.query(Document).order_by(Document.id).all()
        print(f"Found {len(docs)} valid documents in Database.")
        
        if not docs:
            print("No documents to re-index.")
            return

        # 3. Re-ingest Each
        ingestion = IngestionService(db)
        
        for i, doc in enumerate(docs):
            print(f"[{i+1}/{len(docs)}] Re-processing Doc ID {doc.id}: {doc.filename}...")
            
            file_path = doc.file_path
            if not os.path.exists(file_path):
                print(f"❌ File not found: {file_path}. Skipping.")
                continue
            
            try:
                # A. Delete existing chunks for this doc in DB
                db.execute(text("DELETE FROM document_chunks WHERE document_id = :did"), {"did": doc.id})
                db.commit()
                
                # B. Decide Strategy (Force OCR for PDFs to ensure Vision is used)
                strategy = ingestion._triage_document(file_path)
                if file_path.lower().endswith('.pdf'):
                    strategy = 'OCR'
                print(f"   -> Strategy: {strategy}")
                
                # C. Process Stream
                chunk_buffer = []
                BATCH_SIZE = 32
                is_first_batch = True
                global_chunk_index = 0
                
                async for page_data in ingestion._process_stream(doc.id, file_path, strategy):
                     # Chunking
                     page_chunks = await asyncio.get_running_loop().run_in_executor(None, ingestion._chunk_text, [page_data])
                     if not page_chunks: continue
                     
                     chunk_buffer.extend(page_chunks)
                     
                     while len(chunk_buffer) >= BATCH_SIZE:
                         batch = chunk_buffer[:BATCH_SIZE]
                         chunk_buffer = chunk_buffer[BATCH_SIZE:]
                         await ingestion._process_batch(doc.id, batch, is_first_batch, global_chunk_index)
                         global_chunk_index += len(batch)
                         is_first_batch = False
                
                # Final Flush
                if chunk_buffer:
                    await ingestion._process_batch(doc.id, chunk_buffer, is_first_batch, global_chunk_index)
                
                print(f"✅ Re-ingested {doc.filename}")
                
            except Exception as e:
                print(f"❌ Error re-processing {doc.id}: {e}")
                db.rollback()
        
        # 4. Rebuild BM25 Index
        # Now that all chunks are in DB, we build the Sparse Index
        print("\n" + "="*30)
        print("4. Building BM25 Sparse Index...")
        try:
             # Fetch all chunks (This might be large, but sparse_bm25 is memory efficient)
             # In production, use iterator or batching if > 100k chunks
             print("   -> Fetching all chunks from DB...")
             all_chunks = db.query(DocumentChunk).all()
             
             if all_chunks:
                 chunk_texts = [c.content for c in all_chunks]
                 chunk_ids = [c.id for c in all_chunks]
                 
                 bm25 = SparseBM25Retriever()
                 bm25.fit(chunk_texts, chunk_ids)
                 
                 settings = get_settings()
                 save_path = f"{settings.index_storage_path}.bm25_index"
                 
                 bm25.save(save_path)
                 print(f"✅ BM25 Index built and saved to {save_path}")
                 print(f"   -> Stats: {len(chunk_ids)} chunks indexed.")
             else:
                 print("⚠️ No chunks found to index.")
                 
        except Exception as eObj:
             print(f"❌ Error building BM25: {eObj}")

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(full_reindex())

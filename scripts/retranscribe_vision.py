
import asyncio
import sys
import os
import pdfplumber
import io
import json
from PIL import Image

sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.domain.models import Document, DocumentChunk, DocumentStatus
from app.domain.repositories.document_repository import DocumentRepository
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.application.services.vision_service import VisionService
from sqlalchemy import text as sql_text

DOC_ID = 113
BACKUP_FILE = "transcription_backup.json"

async def retranscribe():
    print(f"🚀 Starting Deep Clean & Re-Transcribe for Doc {DOC_ID}...")
    
    db = SessionLocal()
    try:
        doc_repo = DocumentRepository(db)
        
        doc = doc_repo.get_by_id(DOC_ID)
        if not doc:
            print("❌ Document not found")
            return
            
        print(f" -> Found Document: {doc.filename}")
        
        # 1. Cleanup Old Data
        print(" -> Deleting old chunks (DB + Vector)...")
        # Get old chunk IDs/Vector IDs
        old_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == DOC_ID).all()
        vector_ids = [int(c.vector_id) for c in old_chunks if c.vector_id and c.vector_id.isdigit()]
        
        vec_store = MilvusVectorStore()
        if vector_ids:
             expr = f"id in {vector_ids}"
             await asyncio.to_thread(vec_store.client.delete, collection_name=vec_store.collection_name, filter=expr)
             print(f" -> Deleted {len(vector_ids)} vectors from Milvus")
             
        # RAW SQL DELETE (Force Commit)
        db.execute(sql_text("DELETE FROM document_chunks WHERE document_id = :did"), {"did": DOC_ID})
        db.commit()
        
        # Verify Deletion
        count = db.execute(sql_text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :did"), {"did": DOC_ID}).scalar()
        print(f" -> Post-Delete Count: {count}")
        if count > 0:
             print("❌ CRITICAL: Delete failed! Rows still exist.")
             return
             
        # 2. Vision Transcription (With Cache)
        new_chunks_data = []
        
        if os.path.exists(BACKUP_FILE):
             print(f" -> Found backup {BACKUP_FILE}, skipping Vision AI...")
             with open(BACKUP_FILE, "r") as f:
                 new_chunks_data = json.load(f)
        else:
            print(" -> Processing PDF with Vision AI (Transcription Mode)...")
            vision = VisionService()
            with pdfplumber.open(doc.file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    print(f"   -> Page {i+1}/{len(pdf.pages)}...")
                    
                    im = page.to_image(resolution=300)
                    img_byte_arr = io.BytesIO()
                    im.original.save(img_byte_arr, format='PNG')
                    img_bytes = img_byte_arr.getvalue()
                    
                    text = vision.transcribe_image(img_bytes)
                    
                    # Sanity check: if empty, force describe? No, stick to transcription.
                    if text:
                        print(f"      Extracted {len(text)} chars: {text[:50]}...")
                        new_chunks_data.append({
                            "page": i+1,
                            "content": text
                        })
                    else:
                        print("      [Empty]")
            
            # Save Backup
            with open(BACKUP_FILE, "w") as f:
                json.dump(new_chunks_data, f)
        
        # 3. Embed & Save
        embed_service = EmbeddingService()
        
        texts = [c['content'] for c in new_chunks_data if c['content'].strip()]
        metadatas = [{"page": c['page']} for c in new_chunks_data if c['content'].strip()]
        
        if not texts:
            print("❌ No text extracted at all!")
            return

        print(" -> Generating Embeddings...")
        embeddings = []
        for text in texts:
             vec = await embed_service.embed_text(text)
             embeddings.append(vec)
             
        # 4. Manual ID Allocation (Bypass Oracle Sequence Sync Issues)
        print(" -> Generating IDs manually...")
        # Get Max ID
        res = db.execute(sql_text("SELECT MAX(id) FROM document_chunks"))
        max_id = res.scalar() or 0
        current_id = max_id + 100000
        print(f" -> Starting ID: {current_id} (Offset applied)")
        
        chunks_objs = []
        import hashlib
        for i, text in enumerate(texts):
            # Generate Hash
            c_hash = hashlib.sha256(text.encode()).hexdigest()
            
            chunk = DocumentChunk(
                id=current_id + i, # Explicit ID
                document_id=DOC_ID,
                chunk_index=i,
                content=text,
                content_hash=c_hash, # Explicit Hash
                page_number=metadatas[i]['page'],
                vector_id=str(current_id + i) # Pre-fill vector_id
            )
            db.add(chunk)
            chunks_objs.append(chunk)

        # 5. Insert into Milvus with Known IDs
        print(" -> Inserting into Milvus with synced IDs...")
        milvus_data = []
        
        for i, (c, vec) in enumerate(zip(chunks_objs, embeddings)):
            milvus_data.append({
                "id": c.id,
                "document_id": DOC_ID,
                "embedding": vec
            })
            
        res = await asyncio.to_thread(vec_store.client.insert, collection_name="ioc_document_chunks", data=milvus_data)
        print(f" -> Inserted {res['insert_count']} vectors into Milvus")
        
        # 6. Commit DB (Atomic)
        print(" -> Committing to Postgres...")
        try:
            db.commit()
            print("✅ Re-Transcription & Indexing Complete!")
        except Exception as e_commit:
            print(f"❌ COMMIT ERROR: {e_commit}")
            # Try to print details if available
            if hasattr(e_commit, 'orig') and hasattr(e_commit.orig, 'diag'):
                 print(f"DIAG: {e_commit.orig.diag.message_detail}")
            raise e_commit

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(retranscribe())

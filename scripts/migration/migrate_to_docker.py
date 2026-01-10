import sys
import os
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger
from tqdm import tqdm

# Add app to path
sys.path.append(os.getcwd())

from app.core.config import get_settings
from app.domain.models import DocumentChunk
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from pymilvus import MilvusClient

# Manual Milvus Docker Connection (Target)
DOCKER_MILVUS_URI = "http://localhost:19530"

def migrate_data():
    settings = get_settings()
    logger.info("🚀 Starting Migration: Oracle -> Milvus Docker")
    
    # 1. Connect to Oracle (Source)
    logger.info("Connecting to Oracle DB...")
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # 2. Connect to Milvus Docker (Target)
    # We instantiate a fresh client pointing explicitly to Docker
    logger.info(f"Connecting to Milvus Docker at {DOCKER_MILVUS_URI}...")
    try:
        milvus_client = MilvusClient(uri=DOCKER_MILVUS_URI, token=settings.milvus_token)
    except Exception as e:
        logger.error(f"❌ Failed to connect to Milvus Docker: {e}")
        logger.error("Ensure 'docker-compose -f docker-compose.milvus.yml up -d' is running and healthy.")
        return

    # Ensure Collection in Target
    collection_name = "ioc_document_chunks"
    if not milvus_client.has_collection(collection_name):
        logger.info(f"Creating collection '{collection_name}' in Docker Milvus...")
        # We can reuse the logic from MilvusVectorStore if we imported it, 
        # but to avoid env config conflict (since env points to Lite), 
        # let's replicate the schema creation fast or instantiate store with override if possible?
        # The store class reads from settings singleton. 
        # Safest is to use manual schema setup here to match.
        
        from pymilvus import DataType
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="document_id", datatype=DataType.INT64)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=settings.vector_dimension)
        
        index_params = milvus_client.prepare_index_params()
        index_params.add_index(field_name="embedding", index_type="HNSW", metric_type="L2", params={"M": 16, "efConstruction": 200})
        
        milvus_client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)
        logger.info("✅ Collection created.")
    else:
        logger.info(f"Collection '{collection_name}' already exists.")

    # 3. Initialize Embedding Service
    logger.info("Initializing Embedding Model (this may take a moment)...")
    embedding_service = EmbeddingService()
    
    # 4. Fetch Chunks
    total_chunks = session.query(DocumentChunk).count()
    logger.info(f"Found {total_chunks} chunks to migrate.")
    
    batch_size = 50
    offset = 0
    
    pbar = tqdm(total=total_chunks, desc="Migrating")
    
    while offset < total_chunks:
        chunks = session.query(DocumentChunk).offset(offset).limit(batch_size).all()
        if not chunks:
            break
            
        # Prepare Batch
        texts = [c.content for c in chunks]
        chunk_ids = [c.id for c in chunks]
        doc_ids = [c.document_id for c in chunks]
        
        # Generate Embeddings
        embeddings = embedding_service.embed_batch(texts)
        
        # Insert into Milvus
        data = []
        for i in range(len(chunks)):
            data.append({
                "id": chunk_ids[i],
                "document_id": doc_ids[i],
                "embedding": embeddings[i]
            })
            
        try:
            milvus_client.insert(collection_name=collection_name, data=data)
        except Exception as e:
            logger.error(f"❌ Failed to insert batch at offset {offset}: {e}")
            # Continue or break? 
            # Ideally retry, but for script simplicity we log and simple fail count.
        
        offset += len(chunks)
        pbar.update(len(chunks))
        
    pbar.close()
    
    # 5. Validation
    target_count = milvus_client.query(collection_name=collection_name, filter="", output_fields=["count(*)"])[0]["count(*)"]
    logger.info(f"Migration Complete. Target Collection Count: {target_count}/{total_chunks}")
    
    if target_count == total_chunks:
        logger.info("✅ SUCCESS: Data consistency verified.")
    else:
        logger.warning(f"⚠️ MISMATCH: Expected {total_chunks}, got {target_count}.")

if __name__ == "__main__":
    migrate_data()

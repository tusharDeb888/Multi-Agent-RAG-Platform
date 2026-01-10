import sys
from loguru import logger
from pymilvus import MilvusClient

DOCKER_MILVUS_URI = "http://localhost:19530"

def verify_count():
    logger.info("Connecting to Milvus...")
    client = MilvusClient(uri=DOCKER_MILVUS_URI, token="")
    
    collection_name = "ioc_document_chunks"
    
    logger.info("Forcing flush/compact...")
    client.flush(collection_name)
    
    res = client.query(collection_name=collection_name, filter="", output_fields=["count(*)"])
    count = res[0]["count(*)"]
    
    logger.info(f"Updated Count: {count}")

if __name__ == "__main__":
    verify_count()

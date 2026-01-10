
import sys
import os
sys.path.append(os.getcwd())

from pymilvus import MilvusClient
from app.core.config import get_settings

def check_milvus():
    settings = get_settings()
    try:
        # Connect to Milvus
        client = MilvusClient(uri=settings.milvus_conn_uri, token=settings.milvus_token)
        print(f"Connected to Milvus at {settings.milvus_conn_uri}")
        
        # Check Collections
        collections = client.list_collections()
        print(f"Collections: {collections}")
        
        if "ioc_document_chunks" in collections:
            count = client.query("ioc_document_chunks", filter="", output_fields=["count(*)"])[0]["count(*)"]
            print(f"Count in 'ioc_document_chunks': {count}")
            
            if count > 0:
                # Sample one
                res = client.query("ioc_document_chunks", filter="", limit=1)
                print(f"Sample: {res}")
        else:
            print("Collection 'ioc_document_chunks' NOT found.")
            
    except Exception as e:
        print(f"Error checking Milvus: {e}")

if __name__ == "__main__":
    check_milvus()

import sys
import os
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from pymilvus import MilvusClient

# Workaround for Pydantic/Env loading if needed, but app should handle it
# Initialize verifying duplicate lib ok
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

try:
    from app.core.config import get_settings
    settings = get_settings()
    
    print("--- Configuration ---")
    print(f"Start URI: '{settings.milvus_conn_uri}'")
    print(f"Token: '{settings.milvus_token}'")
    print(f"Index Type: '{settings.vector_index_type}'")
    
    print("\n--- Testing Connection ---")
    try:
        client = MilvusClient(
            uri=settings.milvus_conn_uri,
            token=settings.milvus_token
        )
        print("✅ MilvusClient connected successfully!")
        print(f"Collections: {client.list_collections()}")
    except Exception as e:
        print(f"❌ MilvusClient Failed: {e}")

except Exception as e:
    print(f"❌ Import/Setup Failed: {e}")

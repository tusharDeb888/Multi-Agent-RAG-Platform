
"""
Milvus Vector Store Implementation.
Follows Zero-Trust Architecture:
- Dumb Store: Knows nothing about users/policies.
- Restricted Search: Supports strict ID filtering.
"""
from typing import List, Tuple, Optional, Any
import numpy as np
from loguru import logger
from pymilvus import MilvusClient, DataType

from app.core.config import get_settings
from app.infrastructure.vector_store.base import BaseVectorStore

class MilvusVectorStore(BaseVectorStore):
    """
    Milvus implementation of VectorStore using MilvusClient (New API).
    Enforces 'dumb' storage with strict external ID filtering.
    """
    
    def __init__(self, alias: str = "default"):
        """
        Initialize Milvus Client.
        """
        self.settings = get_settings()
        self.collection_name = "ioc_document_chunks"
        
        # Initialize Client (Handles Lite vs Server automatically based on URI)
        # If uri looks like local file -> Lite. If http -> Server.
        self.client = MilvusClient(
            uri=self.settings.milvus_conn_uri,
            token=self.settings.milvus_token
        )
        
        self._ensure_collection()
        logger.info(f"Milvus Collection '{self.collection_name}' ready.")

    def _ensure_collection(self):
        """Define schema and create collection if not exists."""
        if self.client.has_collection(self.collection_name):
            return

        logger.info(f"Creating Milvus collection: {self.collection_name}")
        
        # Schema is auto-managed by create_collection in simple mode,
        # but for specific schema we use explicit setup.
        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )
        
        # 1. id: Int64 (Matches Oracle Chunk ID)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        # 2. document_id: Int64 (For Filtering)
        schema.add_field(field_name="document_id", datatype=DataType.INT64)
        # 3. embedding: FloatVector
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=self.settings.vector_dimension)
        
        # Indices
        index_params = self.client.prepare_index_params()
        
        # Check if using Lite
        is_lite = self.settings.milvus_conn_uri.startswith(".") or self.settings.milvus_conn_uri.startswith("/")
        
        idx_type = "HNSW" if not is_lite else "AUTOINDEX"
        params = {"M": 16, "efConstruction": 200} if not is_lite else {}
        metric = "L2"
        
        index_params.add_index(
            field_name="embedding", 
            index_type=idx_type,
            metric_type=metric,
            params=params
        )
        
        # Scalar index (Auto in 2.4+, but explicit is fine)
        # index_params.add_index(field_name="document_id", index_type="STL_SORT") 
        
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params
        )

    def add_vectors(self, vectors: np.ndarray, ids: List[int], metadata: Optional[List[dict]] = None) -> None:
        """
        Add vectors to Milvus.
        """
        if not metadata or len(metadata) != len(ids):
            raise ValueError("Metadata with 'document_id' is required for strict lineage.")
            
        doc_ids = [m.get("document_id") for m in metadata]
        if any(d is None for d in doc_ids):
             raise ValueError("All vectors must have a 'document_id'.")
        
        # Prepare Data: List of Dicts for MilvusClient
        data = []
        for i, vec in enumerate(vectors):
            data.append({
                "id": ids[i],
                "document_id": doc_ids[i],
                "embedding": vec.tolist()
            })
        
        try:
            res = self.client.insert(
                collection_name=self.collection_name,
                data=data
            )
            # logger.info(f"Inserted {res['insert_count']} vectors.")
        except Exception as e:
            logger.error(f"Milvus Insert Failed: {e}")
            raise

    def search(self, query_vector: np.ndarray, top_k: int, filter_ids: Optional[List[int]] = None) -> List[Tuple[int, float]]:
        """
        Search with strict RBAC filtering.
        """
        # 1. Zero-Trust Short Circuit
        if filter_ids is not None:
            if len(filter_ids) == 0:
                logger.warning("Milvus Search Blocked: User has 0 accessible documents (Phase 1).")
                return []
                
        # 2. Construct Filter
        filter_str = ""
        if filter_ids:
            filter_str = f"document_id in {str(filter_ids)}"
        
        # 3. Search
        try:
             # Check params based on Lite/Full (Approximate check or just generic params)
            is_lite = self.settings.milvus_conn_uri.startswith(".") or self.settings.milvus_conn_uri.startswith("/")
            search_params = {"metric_type": "L2", "params": {"ef": 100}} if not is_lite else {"metric_type": "L2", "params": {}}
            
            results = self.client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                filter=filter_str,
                limit=top_k,
                output_fields=["id", "document_id"],
                search_params=search_params
            )
            
            # 4. Parse
            hits = results[0]
            parsed_results = []
            for hit in hits:
                # hit is dict in MilvusClient: {'id': 1, 'distance': 0.5, 'entity': {...}}
                parsed_results.append((hit['id'], hit['distance'])) # Note: distance vs score
            
            return parsed_results
            
        except Exception as e:
            logger.error(f"Milvus Search Error: {e}")
            return []

    def delete_vectors(self, ids: List[int]) -> None:
        """Delete vectors by ID."""
        if not ids:
            return
        
        filter_str = f"id in {str(ids)}"
        try:
            self.client.delete(
                collection_name=self.collection_name,
                filter=filter_str
            )
            logger.info(f"Deleted {len(ids)} vectors.")
        except Exception as e:
            logger.error(f"Milvus Delete Failed: {e}")
            raise
            
    def get_vector(self, id: int) -> Optional[np.ndarray]:
        """Fetch single vector."""
        try:
            res = self.client.get(
                collection_name=self.collection_name,
                ids=[id],
                output_fields=["embedding"]
            )
            if not res:
                return None
            return np.array(res[0]["embedding"])
        except Exception:
            return None

    def save(self, path: str) -> None:
        pass
    
    def load(self, path: str) -> None:
        pass

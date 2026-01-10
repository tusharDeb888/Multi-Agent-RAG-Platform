"""
Semantic Cache Service.
Implements a Vector-based Cache using Milvus to serve frequent queries instantly.
"""
import json
import time
import asyncio
from typing import Optional, Dict, Any, List
import numpy as np
from loguru import logger
from pymilvus import MilvusClient, DataType

from app.core.config import get_settings
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.application.api.deps import get_embedding_service

class SemanticCacheService:
    """
    Service for semantic caching of RAG responses.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.collection_name = "ioc_semantic_cache"
        self.embedding_service = get_embedding_service()
        
        # Initialize Client 
        self.client = MilvusClient(
            uri=self.settings.milvus_conn_uri,
            token=self.settings.milvus_token
        )
        
        # Ensure collection exists
        self._ensure_collection()
        logger.info(f"Semantic Cache '{self.collection_name}' ready.")

    def _ensure_collection(self):
        """Define schema and create collection if not exists."""
        if self.client.has_collection(self.collection_name):
            return

        logger.info(f"Creating Semantic Cache collection: {self.collection_name}")
        
        schema = MilvusClient.create_schema(
            auto_id=True,
            enable_dynamic_field=False
        )
        
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="query_vector", datatype=DataType.FLOAT_VECTOR, dim=self.settings.vector_dimension)
        schema.add_field(field_name="original_query", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="response_json", datatype=DataType.VARCHAR, max_length=65535) # Expanded for long JSONs
        schema.add_field(field_name="timestamp", datatype=DataType.INT64)
        
        index_params = self.client.prepare_index_params()
        
        is_lite = self.settings.milvus_conn_uri.startswith(".") or self.settings.milvus_conn_uri.startswith("/")
        idx_type = "HNSW" if not is_lite else "AUTOINDEX"
        params = {"M": 8, "efConstruction": 64} if not is_lite else {} # Lighter index for cache
        
        index_params.add_index(
            field_name="query_vector", 
            index_type=idx_type,
            metric_type="L2",
            params=params
        )
        
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong"
        )

    async def check_cache(self, query: str, threshold: float = 0.2) -> Optional[Dict[str, Any]]:
        """
        Check cache for a comprehensive semantic match.
        Threshold: L2 Distance (Lower is better). 0.2 implies very high similarity.
        """
        try:
            # 1. Embed Query
            query_vector = await self.embedding_service.embed_text(query)
            
            # 2. Search
            # Offload to thread
            search_res = await asyncio.to_thread(
                self.client.search,
                collection_name=self.collection_name,
                data=[query_vector],
                limit=1,
                output_fields=["response_json", "original_query", "timestamp", "id"],
                search_params={"metric_type": "L2", "params": {"ef": 20}}
            )
            
            if not search_res or not search_res[0]:
                return None
            
            match = search_res[0][0]
            score = match['distance'] # L2 Distance
            
            # 3. Validation
            # Match strictly (e.g. 0.1 = ~0.95 Cosine Sim equivalent roughly depending on normalization)
            # Assuming normalized vectors: L2 = 2(1 - Cosine). 0.1 L2 -> 0.05 (1-Cos) -> 0.95 Cosine.
            # So 0.35 is about 0.82. Let's start conservative: 0.2
            if score < threshold:
                logger.info(f"Semantic Cache HIT: '{query}' ~= '{match['entity']['original_query']}' (Dist: {score:.4f})")
                try:
                    return json.loads(match['entity']['response_json'])
                except json.JSONDecodeError:
                    return None
            
            logger.debug(f"Semantic Cache MISS: Closest '{match['entity']['original_query']}' (Dist: {score:.4f})")
            return None
            
        except Exception as e:
            logger.error(f"Semantic Cache Check Failed: {e}")
            return None

    async def cache_response(self, query: str, response_data: Dict[str, Any]) -> None:
        """
        Cache a response asynchronously.
        """
        try:
            # Prevent caching failures/empty responses
            if not response_data.get("answer") or "No grounded information" in response_data.get("answer"):
                return

            # Embed
            query_vector = await self.embedding_service.embed_text(query)
            
            data = [{
                "query_vector": query_vector.tolist() if hasattr(query_vector, "tolist") else query_vector,
                "original_query": query,
                "response_json": json.dumps(response_data),
                "timestamp": int(time.time())
            }]
            
            # Insert
            await asyncio.to_thread(
                self.client.insert,
                collection_name=self.collection_name,
                data=data
            )
            logger.debug(f"Cached response for query: '{query}'")
            
        except Exception as e:
            logger.error(f"Semantic Cache Write Failed: {e}")

    async def cleanup(self):
        """Close connection."""
        if hasattr(self.client, "close"):
            self.client.close()

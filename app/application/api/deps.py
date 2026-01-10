"""
API Dependencies.
Follows Dependency Injection principle.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError
from loguru import logger

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.domain.models import User
from app.domain.repositories.user_repository import UserRepository
from app.application.services.ingestion_service import IngestionService
from app.application.services.rag_service import RAGService
from app.application.services.rbac_service import RBACService
from app.application.services.audit_service import AuditService
from app.infrastructure.embeddings.embedding_service import EmbeddingService

from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.vector_store.base import BaseVectorStore

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Get current authenticated user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
        
    user_repo = UserRepository(db)
    user = user_repo.get_by_username(username)
    
    if user is None:
        raise credentials_exception
        
    if not user.is_active or user.is_deleted:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user

def get_current_user_flexible(
    db: Session = Depends(get_db),
    header_token: Optional[str] = Depends(oauth2_scheme_optional),
    query_token: Optional[str] = Query(None, alias="token")
) -> User:
    """
    Get current user from Header OR Query Param.
    Useful for file downloads/viewing where headers are not easily set.
    """
    token = header_token or query_token
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return get_current_user(db, token)

# Singleton instances
_embedding_service: Optional[EmbeddingService] = None
_vector_store: Optional[BaseVectorStore] = None

def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        logger.info("Initializing Global Embedding Service...")
        _embedding_service = EmbeddingService()
    return _embedding_service

def get_vector_store() -> BaseVectorStore:
    global _vector_store
    if _vector_store is None:
        logger.info("Initializing Global Vector Store...")
        settings = get_settings()
        if settings.vector_index_type.value == "milvus":
             from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
             _vector_store = MilvusVectorStore()
        elif settings.vector_index_type.value == "oracle_vector":
             from app.infrastructure.vector_store.oracle_store import OracleVectorStore
             _vector_store = OracleVectorStore()
        else:
             logger.error(f"Unknown or unsupported vector store type {settings.vector_index_type}")
             # Defaulting to Milvus if allowed, or raising error
             raise NotImplementedError("FAISS support removed. Please configure Milvus.")
    return _vector_store

def get_ingestion_service(
    db: Session = Depends(get_db),
    # Inject Singletons to prevent creating new connections per request
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store: BaseVectorStore = Depends(get_vector_store)
) -> IngestionService:
    """Get IngestionService instance via DI."""
    return IngestionService(
        db, 
        embedding_service=embedding_service,
        vector_store=vector_store
    )

def get_rag_service(db: Session = Depends(get_db)) -> RAGService:
    """Get RAGService instance using Singletons."""
    return RAGService(
        db,
        llm_adapter=LLMFactory.create_llm_adapter(),
        embedding_service=get_embedding_service(),
        vector_store=get_vector_store()
    )

def get_rbac_service(db: Session = Depends(get_db)) -> RBACService:
    """Get RBACService instance."""
    return RBACService(db)

def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    """Get AuditService instance."""
    return AuditService(db)

# Singleton
_cache_service: Optional[any] = None

def get_cache_service() -> any:
    """Get CacheService singleton."""
    global _cache_service
    if _cache_service is None:
        from app.infrastructure.cache.cache_service import CacheService
        logger.info("Initializing Global Cache Service...")
        _cache_service = CacheService()
    return _cache_service

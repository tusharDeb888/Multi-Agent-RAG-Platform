"""
RBAC Service for access control.
Follows Single Responsibility Principle - only handles authorization.
"""
from typing import List, Set
from sqlalchemy.orm import Session
from loguru import logger

from app.domain.models import User, UserRole
from app.domain.repositories.user_repository import UserRepository
from app.domain.repositories.access_policy_repository import (
    DocumentAccessPolicyRepository,
    ChunkAccessPolicyRepository
)


class RBACService:
    """
    Role-Based Access Control service.
    Handles permission checking and filtering.
    """
    
    def __init__(self, db: Session):
        """
        Initialize RBAC service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.user_repo = UserRepository(db)
        self.doc_policy_repo = DocumentAccessPolicyRepository(db)
        self.chunk_policy_repo = ChunkAccessPolicyRepository(db)
    
    def get_user_roles(self, user_id: int) -> List[int]:
        """
        Get role IDs for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of role IDs
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return []
        
        return [role.role_id for role in user.roles]
    
    def can_access_document(self, user_id: int, document_id: int) -> bool:
        """
        Check if user can access a document.
        
        Args:
            user_id: User ID
            document_id: Document ID
            
        Returns:
            True if user can access, False otherwise
        """
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            return False
        
        # Super admin has access to everything
        user_roles = self.get_user_roles(user_id)
        role_names = [role.role.name for role in user.roles]
        if UserRole.SUPER_ADMIN.value in role_names:
            return True
        
        # Check document-level policies
        accessible_docs = self.doc_policy_repo.get_accessible_documents(
            user_id=user_id,
            user_department_id=user.department_id,
            user_role_ids=user_roles
        )
        
        return document_id in accessible_docs
    
    
    # Clearance Hierarchy Mapping (Higher is more secure)
    CLEARANCE_HIERARCHY = {
        "public": 0,
        "internal": 1,
        "confidential": 2,
        "restricted": 3
    }
    
    def _rank(self, level) -> int:
        """Helper to get integer rank of a classification level."""
        # Level can be an Enum or string
        val = str(level).lower().split(".")[-1] # Handle Enum.VALUE -> value
        return self.CLEARANCE_HIERARCHY.get(val, 1) # Default to Internal (1)
    
    def filter_accessible_documents(self, user_id: int, document_ids: List[int]) -> List[int]:
        """
        Filter document IDs to only those accessible to the user (Role + Clearance).
        """
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
             return []
        
        # Super admin bypass
        role_names = [role.role.name for role in user.roles]
        if UserRole.SUPER_ADMIN.value in role_names:
            return document_ids

        # 1. Base Role/Dept Policy Filter
        accessible_docs = self.doc_policy_repo.get_accessible_documents(
            user_id=user_id,
            user_department_id=user.department_id,
            user_role_ids=self.get_user_roles(user_id)
        )
        accessible_set = set(accessible_docs)
        
        # 2. Clearance Filter (MAC)
        # We need to fetch the classification of the candidate documents
        candidate_ids = [doc_id for doc_id in document_ids if doc_id in accessible_set]
        
        if not candidate_ids:
            return []
            
        from app.domain.models import Document, ClassificationLevel
        
        # Fetch Classifications
        docs = self.db.query(Document.id, Document.classification).filter(
            Document.id.in_(candidate_ids)
        ).all()
        
        user_clearance_rank = self._rank(user.clearance_level)
        
        final_ids = []
        for doc_id, classification in docs:
            doc_rank = self._rank(classification)
            if user_clearance_rank >= doc_rank:
                final_ids.append(doc_id)
            else:
                logger.warning(f"Access Denied: User {user_id} (Clearance {user_clearance_rank}) tried to access Doc {doc_id} (Class {doc_rank})")

        return final_ids
    
    def filter_accessible_chunks(self, user_id: int, chunk_ids: List[int]) -> List[int]:
        """
        Filter chunk IDs to only those accessible to the user (Role + Clearance).
        Note: Chunks inherit classification from their parent Document.
        """
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            return []
        
        # Super admin bypass
        role_names = [role.role.name for role in user.roles]
        if UserRole.SUPER_ADMIN.value in role_names:
            return chunk_ids
        
        # 1. Phase 1: Policy Decision (Document Level)
        # Get authoritative list of allowed documents
        allowed_doc_ids = self.doc_policy_repo.get_accessible_documents(
            user_id=user_id,
            user_department_id=user.department_id,
            user_role_ids=self.get_user_roles(user_id)
        )
        
        # 2. Phase 2: Constrained Retrieval (Chunk Level)
        # Strictly filter chunks that belong to allowed documents
        accessible_chunk_ids = self.chunk_policy_repo.get_accessible_chunks(
             chunk_ids=chunk_ids,
             allowed_document_ids=allowed_doc_ids
        )
        
        if not accessible_chunk_ids:
            return []
            
        # 2. Clearance Filter (Join with Document to check Classification)
        from app.domain.models import DocumentChunk, Document
        
        candidate_chunks = self.db.query(DocumentChunk.id, Document.classification)\
            .join(Document, DocumentChunk.document_id == Document.id)\
            .filter(DocumentChunk.id.in_(accessible_chunk_ids))\
            .all()
            
        user_clearance_rank = self._rank(user.clearance_level)
        
        final_ids = []
        for chunk_id, classification in candidate_chunks:
            doc_rank = self._rank(classification)
            if user_clearance_rank >= doc_rank:
                final_ids.append(chunk_id)
        
        return final_ids
    
    def has_role(self, user_id: int, role_name: str) -> bool:
        """
        Check if user has a specific role.
        
        Args:
            user_id: User ID
            role_name: Role name to check
            
        Returns:
            True if user has the role, False otherwise
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False
        
        role_names = [role.role.name for role in user.roles]
        return role_name in role_names
    
    def get_accessible_chunk_ids(self, user_id: int) -> List[int]:
        """
        Get all chunk IDs accessible to the user (Pre-calculation for Vector Search).
        """
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            return []
        
        # Super admin bypass
        role_names = [role.role.name for role in user.roles]
        if UserRole.SUPER_ADMIN.value in role_names:
            return None # None means "All" / No Filter
            
        # 1. Get Allowed Docs (Phase 1)
        allowed_doc_ids = self.doc_policy_repo.get_accessible_documents(
            user_id=user_id,
            user_department_id=user.department_id,
            user_role_ids=self.get_user_roles(user_id)
        )
        
        if not allowed_doc_ids:
            return []
            
        # 2. Get Chunks for Docs
        chunk_ids = self.chunk_policy_repo.get_chunks_for_documents(allowed_doc_ids)
        return chunk_ids





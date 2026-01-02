"""
Access policy repository for RBAC.
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.domain.models import DocumentAccessPolicy, ChunkAccessPolicy, User, Role, Document, Department, document_departments


class DocumentAccessPolicyRepository:
    """Repository for document access policies."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_policies_for_document(self, document_id: int) -> List[DocumentAccessPolicy]:
        """Get all access policies for a document."""
        return self.db.query(DocumentAccessPolicy).filter(
            DocumentAccessPolicy.document_id == document_id
        ).all()
    
    def get_accessible_documents(
        self, 
        user_id: int, 
        user_department_id: Optional[int], 
        user_role_ids: List[int]
    ) -> List[int]:
        """
        Get list of document IDs accessible to a user.
        
        Args:
            user_id: User ID
            user_department_id: User's department ID
            user_role_ids: List of user's role IDs
            
        Returns:
            List of accessible document IDs
        """
        now = datetime.utcnow()
        
        # Build query for accessible documents
        query = self.db.query(DocumentAccessPolicy.document_id).filter(
            or_(
                # User-specific access
                DocumentAccessPolicy.user_id == user_id,
                # Department-based access
                DocumentAccessPolicy.department_id == user_department_id,
                # Role-based access
                DocumentAccessPolicy.role_id.in_(user_role_ids) if user_role_ids else False
            ),
            # Time-based validity
            or_(
                DocumentAccessPolicy.valid_from.is_(None),
                DocumentAccessPolicy.valid_from <= now
            ),
            or_(
                DocumentAccessPolicy.valid_until.is_(None),
                DocumentAccessPolicy.valid_until >= now
            )
        ).distinct()
        
        # 1. IDs from Explicit Policies
        explicit_ids = [doc_id for (doc_id,) in query.all()]
        
        # 2. IDs from Implicit Department Access (M2M) + General
        # Query Documents where:
        #   - Linked to User's Department
        #   - OR Linked to 'General' Department
        
        implicit_query = self.db.query(Document.id).join(
            document_departments, Document.id == document_departments.c.document_id
        ).join(
            Department, Department.id == document_departments.c.department_id
        ).filter(
            or_(
                Department.id == user_department_id,
                Department.name == "General"
            )
        )
        
        implicit_ids = [doc_id for (doc_id,) in implicit_query.all()]
        
        # Combine and Deduplicate
        return list(set(explicit_ids + implicit_ids))


class ChunkAccessPolicyRepository:
    """Repository for chunk access policies."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_accessible_chunks(
        self,
        chunk_ids: List[int],
        allowed_document_ids: List[int]
    ) -> List[int]:
        """
        Phase 2: Constrained Retrieval.
        Filter chunk IDs to Ensure they belong to allowed documents.
        
        Args:
            chunk_ids: Candidate chunk IDs from vector search
            allowed_document_ids: List of document IDs approved in Phase 1
            
        Returns:
            List of accessible chunk IDs
        """
        if not chunk_ids or not allowed_document_ids:
            return []
        
        # Optimization: If very few chunks, do it in memory? 
        # But SQL is safer for consistency.
        
        from app.domain.models import DocumentChunk
        
        query = self.db.query(DocumentChunk.id).filter(
            DocumentChunk.id.in_(chunk_ids),
            DocumentChunk.document_id.in_(allowed_document_ids)
        )
        
        return [chunk_id for (chunk_id,) in query.all()]

    def get_chunks_for_documents(self, document_ids: List[int]) -> List[int]:
        """
        Helper to get all chunk IDs for a list of documents.
        Used for Vector Store pre-filtering.
        """
        if not document_ids:
            return []
            
        from app.domain.models import DocumentChunk
        # Optimize: If too many docs, might need batching, but for now direct IN is fine
        query = self.db.query(DocumentChunk.id).filter(
            DocumentChunk.document_id.in_(document_ids)
        )
        return [chunk_id for (chunk_id,) in query.all()]





"""
Document repository for data access.
Follows Repository Pattern.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.domain.models import Document, DocumentStatus, ClassificationLevel, Department
from app.domain.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Repository for document operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Document)
    
    def get_by_status(self, status: DocumentStatus) -> List[Document]:
        """Get documents by status."""
        return self.db.query(Document).filter(Document.status == status).all()
    
    def get_by_department(self, department_name: str) -> List[Document]:
        """Get documents by department."""
        return self.db.query(Document).join(Document.department).filter(Department.name == department_name).all()
    
    def get_by_classification(self, classification: ClassificationLevel) -> List[Document]:
        """Get documents by classification level."""
        return self.db.query(Document).filter(Document.classification == classification).all()
    
    def get_by_uploader(self, user_id: int) -> List[Document]:
        """Get documents uploaded by a user."""
        return self.db.query(Document).filter(Document.uploaded_by == user_id).all()
    
        return self.db.query(Document).filter(
            Document.filename.like(f"%{filename_pattern}%")
        ).all()
        
    def get_by_hash(self, content_hash: str) -> Optional[Document]:
        """Get document by content hash (deduplication check)."""
        return self.db.query(Document).filter(Document.content_hash == content_hash).first()





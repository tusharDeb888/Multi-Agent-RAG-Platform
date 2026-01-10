"""
Document repository for data access.
Follows Repository Pattern.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from loguru import logger

from app.domain.models import Document, DocumentStatus, ClassificationLevel, Department, User
from app.domain.repositories.base import BaseRepository



DEFAULT_DEPARTMENT = "General"
MAX_SEARCH_LIMIT = 1000
BATCH_SIZE = 500

class DocumentRepository(BaseRepository[Document]):
    """Repository for document operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Document)
    
    def get_by_status(self, status: DocumentStatus, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get documents by status with pagination."""
        return self.db.query(Document).filter(
            Document.status == status
        ).order_by(Document.id.desc()).offset(skip).limit(limit).all()
    
    def get_by_department(self, department_name: str, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get documents by department (Including General) with pagination."""
        return self.db.query(Document).filter(
            Document.departments.any(
                or_(
                    Department.name == department_name,
                    Department.name == DEFAULT_DEPARTMENT
                )
            )
        ).order_by(Document.id.desc()).offset(skip).limit(limit).all()
    
    def get_by_classification(self, classification: ClassificationLevel, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get documents by classification level with pagination."""
        return self.db.query(Document).filter(
            Document.classification == classification
        ).order_by(Document.id.desc()).offset(skip).limit(limit).all()
    
    def get_by_uploader(self, user_id: int, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get documents uploaded by a user with pagination."""
        return self.db.query(Document).filter(
            Document.uploaded_by == user_id
        ).order_by(Document.id.desc()).offset(skip).limit(limit).all()
    
    def search_by_filename(self, filename_pattern: str, limit: int = 100) -> List[Document]:
        """
        Search documents by filename pattern.
        Args:
            filename_pattern: SQL LIKE pattern 
            limit: Max results to return (default 100, max 1000)
        """
        # Escape special characters to prevent wildcard injection/DoS
        safe_pattern = filename_pattern.replace("%", "\\%").replace("_", "\\_")
        return self.db.query(Document).filter(
            Document.filename.ilike(f"%{safe_pattern}%", escape="\\")
        ).limit(min(limit, MAX_SEARCH_LIMIT)).all()
        
    def get_by_hash(self, content_hash: str, lock: bool = False) -> Optional[Document]:
        """
        Get document by content hash (deduplication check).
        Use lock=True for 'Check-then-Insert' logic to prevent race conditions.
        """
        query = self.db.query(Document).filter(Document.content_hash == content_hash)
        if lock:
            query = query.with_for_update()
        return query.first()

    def get_by_ids(self, doc_ids: List[int]) -> List[Document]:
        """
        Get documents by IDs.
        Includes batching to avoid SQL 'IN' clause limits.
        """
        if not doc_ids:
            return []
            
        results = []
        for i in range(0, len(doc_ids), BATCH_SIZE):
            batch = doc_ids[i:i + BATCH_SIZE]
            batch_results = self.db.query(Document).filter(
                Document.id.in_(batch)
            ).all()
            results.extend(batch_results)
            
        # Sort results to match input order
        doc_map = {d.id: d for d in results}
        return [doc_map[did] for did in doc_ids if did in doc_map]

    def delete_by_ids(self, ids: List[int]) -> List[int]:
        """
        Bulk delete documents by IDs.
        Does NOT match/delete chunks (Service layer responsibility via ChunkRepository).
        Does NOT commit.
        """
        if not ids:
            return []
            
        deleted_ids = []
        # Process in batches
        for i in range(0, len(ids), BATCH_SIZE):
            batch = ids[i:i + BATCH_SIZE]
            
            # Select with lock first
            documents = self.db.query(Document).filter(
                Document.id.in_(batch)
            ).with_for_update().all()
            
            found_ids = [d.id for d in documents]
            if found_ids:
                self.db.query(Document).filter(
                    Document.id.in_(found_ids)
                ).delete(synchronize_session=False)
                deleted_ids.extend(found_ids)
                
        logger.info(f"Bulk deleted {len(deleted_ids)} documents (SQL only)")
        return deleted_ids
    def delete(self, id: int) -> bool:
        """
        Delete a document by ID.
        Delegates to delete_by_ids for consistent locking and vector ID handling (though handled by service).
        Does NOT commit.
        """
        deleted_ids = self.delete_by_ids([id])
        return len(deleted_ids) > 0

    def create(self, entity: Document) -> Document:
        """Disable inherited create to prevent accidental commits."""
        raise NotImplementedError("Use add() and commit externally.")

    def update(self, entity: Document) -> Document:
        """Disable inherited update to prevent accidental commits."""
        raise NotImplementedError("Manage updates via session and commit externally.")

    def add_all(self, documents: List[Document]) -> List[Document]:
        """
        Add multiple documents (Bulk Insert).
        Locks User rows to prevent concurrency race conditions (double submission).
        Checks for duplicate content_hashes.
        Uses batching to avoid SQL query limits.
        """
        if not documents:
            return []
            
        # Deadlock Prevention: Globally sort documents by uploader to ensure consistent lock acquisition order across all batches.
        # This prevents scenarios where Transaction A processes [User1, User2] and Transaction B processes [User2, User1]
        # split across different batches, leading to a deadlock.
        documents.sort(key=lambda x: x.uploaded_by)
        
        # Process in batches to avoid SQL limit issues with IN clauses
        for i in range(0, len(documents), BATCH_SIZE):
            batch = documents[i:i + BATCH_SIZE]
            
            # 1. Lock Users to serialize uploads per user (Prevent double-submit race)
            user_ids = sorted(list({d.uploaded_by for d in batch}))
            if user_ids:
                self.db.query(User).filter(User.id.in_(user_ids)).with_for_update().all()
            
            # 2. Check for duplicates in the database
            hashes = [d.content_hash for d in batch if d.content_hash]
            
            # 2a. Intra-Batch Duplicate Check
            if len(hashes) != len(set(hashes)):
                 error_msg = "Duplicate documents found in the input batch."
                 logger.error(error_msg)
                 raise ValueError(error_msg)

            if hashes:
                existing = self.db.query(Document).filter(
                    Document.content_hash.in_(hashes)
                ).first()
                
                if existing:
                    error_msg = f"Document with hash {existing.content_hash} already exists."
                    logger.error(error_msg)
                    raise ValueError(error_msg)

            # 3. Insert and Flush per batch
            self.db.add_all(batch)
            self.db.flush() # Ensure IDs are generated for this batch

        return documents

    def add(self, entity: Document) -> Document:
        """
        Add a new document.
        Wraps add_all to enforce policy consistency.
        """
        self.add_all([entity])
        return entity





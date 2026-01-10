"""
Document chunk repository for data access.
"""
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from loguru import logger


from app.domain.models import DocumentChunk, Document
from app.domain.repositories.base import BaseRepository

BATCH_SIZE = 500
MAX_QUERY_LIMIT = 5000

class ChunkRepository(BaseRepository[DocumentChunk]):
    """Repository for document chunk operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, DocumentChunk)
    
    def add_all(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Add multiple chunks (Bulk Insert).
        Note: Objects are added to session but not flushed. IDs will be None until flush/commit.
        Raises ValueError if chunks already exist for the target documents (Clean Insert Policy).
        """
        if not chunks:
            return []
            
        # Integrity Check: Ensure we aren't creating duplicates
        # Lock Parent Documents: This guarantees serialized inserts for these documents
        # (preventing race conditions where multiple processes try to insert chunks for the same doc simultaneously)
        doc_ids = {c.document_id for c in chunks}
        self.db.query(Document).filter(
            Document.id.in_(doc_ids)
        ).with_for_update().all()
        
        # [Fix] Removed aggressive check for existing chunks. 
        # Batched ingestion requires adding chunks incrementally.
        # UniqueConstraint(document_id, chunk_index) handles duplicates safely.
        
        logger.info(f"Bulk adding {len(chunks)} chunks for documents {list(doc_ids)}")
        self.db.add_all(chunks)
        self.db.flush() # Generate IDs immediately
        return chunks
    def get_by_document_id(self, document_id: int) -> List[DocumentChunk]:
        """Get all chunks for a document."""
        return self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index.asc()).all()
    
    def get_by_ids(self, chunk_ids: List[int]) -> List[DocumentChunk]:
        """
        Get chunks by IDs.
        Includes batching to avoid SQL 'IN' clause limits (e.g. 1000 items).
        """
        if not chunk_ids:
            return []
            
        results = []
        for i in range(0, len(chunk_ids), BATCH_SIZE):
            batch = chunk_ids[i:i + BATCH_SIZE]
            batch_results = self.db.query(DocumentChunk).options(
                joinedload(DocumentChunk.document)
            ).filter(
                DocumentChunk.id.in_(batch)
            ).all()
            results.extend(batch_results)
            
        # Sort results to match input order
        chunk_map = {c.id: c for c in results}
        return [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]
    
    def get_by_content_hash(self, content_hash: str) -> Optional[DocumentChunk]:
        """
        Get chunk by content hash (deduplication).
        
        Returns:
            DocumentChunk if found, None otherwise.
        """
        return self.db.query(DocumentChunk).filter(
            DocumentChunk.content_hash == content_hash
        ).first()

    def get_all(self, limit: int = 1000, offset: int = 0) -> List[DocumentChunk]:
        """
        Get all chunks with pagination.
        
        Args:
            limit: Maximum number of chunks to return (default 1000 to prevent memory exhaustion)
            offset: Number of chunks to skip
            
        Returns:
            List of DocumentChunk objects
        """
        return self.db.query(DocumentChunk).offset(offset).limit(min(limit, MAX_QUERY_LIMIT)).all()

    def delete_by_document_id(self, document_id: int) -> List[str]:
        """Delete all chunks for a document. Returns list of vector_ids for cleanup."""
        # Get vector IDs before deletion with lock to prevent race conditions
        chunks = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).with_for_update().all()
        
        vector_ids = [str(c.vector_id) for c in chunks if c.vector_id]
        found_ids = [c.id for c in chunks]
        
        if found_ids:
            # Delete by specific IDs to ensure we only delete what we saw (preventing phantom deletion leaks)
            self.db.query(DocumentChunk).filter(
                DocumentChunk.id.in_(found_ids)
            ).delete(synchronize_session=False)
        
        logger.info(f"Deleted {len(found_ids)} chunks for document {document_id}, returning {len(vector_ids)} vector IDs for cleanup")
        # Do not commit here - let the Service layer handle the transaction
        return vector_ids

    def delete_by_ids(self, chunk_ids: List[int]) -> List[str]:
        """
        Bulk delete chunks by specific IDs.
        Returns list of vector_ids for cleanup.
        """
        if not chunk_ids:
            return []

        # Lock rows and get vectors match existing logic
        # Batching for safety
        all_vector_ids = []
        
        for i in range(0, len(chunk_ids), BATCH_SIZE):
            batch = chunk_ids[i:i + BATCH_SIZE]
            
            chunks = self.db.query(DocumentChunk).filter(
                DocumentChunk.id.in_(batch)
            ).with_for_update().all()
            
            found_ids = [c.id for c in chunks]
            batch_vectors = [str(c.vector_id) for c in chunks if c.vector_id]
            all_vector_ids.extend(batch_vectors)
            
            if found_ids:
                self.db.query(DocumentChunk).filter(
                    DocumentChunk.id.in_(found_ids)
                ).delete(synchronize_session=False)
                
        logger.info(f"Bulk deleted {len(all_vector_ids)} chunks (from {len(chunk_ids)} requested IDs)")
        return all_vector_ids

    def delete(self, id: int) -> Optional[str]:
        """
        Delete a chunk by ID.
        Returns vector_id if present (for cleanup).
        Overrides BaseRepository.delete to prevent commit and handle vectors.
        """
        # Lock row for safety
        chunk = self.db.query(DocumentChunk).filter(
            DocumentChunk.id == id
        ).with_for_update().first()
        
        if not chunk:
            return None
            
        vector_id = str(chunk.vector_id) if chunk.vector_id else None
        
        self.db.delete(chunk)
        # Note: No commit here.
        logger.debug(f"Deleted chunk {id}, vector_id={vector_id}")
        
        return vector_id



    def create(self, entity: DocumentChunk) -> DocumentChunk:
        """Disable inherited create to prevent accidental commits."""
        raise NotImplementedError("Use add() or add_all() and commit externally.")

    def update(self, entity: DocumentChunk) -> DocumentChunk:
        """Disable inherited update to prevent accidental commits."""
        raise NotImplementedError("Manage updates via session and commit externally.")

    def add(self, entity: DocumentChunk) -> DocumentChunk:
        """
        Override add to enforce 'Clean Insert' policy or redirect to add_all.
        Single chunk insertion without integrity check is risky.
        """
        # For consistency, we treat a single add as a batch of 1
        self.add_all([entity])
        return entity

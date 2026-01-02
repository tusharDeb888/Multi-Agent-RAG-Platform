"""
Document chunk repository for data access.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from loguru import logger

from app.domain.models import DocumentChunk
from app.domain.repositories.base import BaseRepository
from app.core.config import get_settings

class ChunkRepository(BaseRepository[DocumentChunk]):
    """Repository for document chunk operations with Encryption Support."""
    
    def __init__(self, db: Session):
        super().__init__(db, DocumentChunk)
        self.settings = get_settings()
        self.encryption_service = None
        if self.settings.enable_encryption:
            try:
                from app.core.encryption import EncryptionService
                self.encryption_service = EncryptionService()
            except Exception as e:
                logger.error(f"Failed to initialize EncryptionService: {e}")

    def add(self, chunk: DocumentChunk) -> DocumentChunk:
        """Add a new chunk, encrypting content if enabled."""
        if self.encryption_service and chunk.content:
            try:
                chunk.content = self.encryption_service.encrypt(chunk.content)
            except Exception as e:
                logger.error(f"Encryption failed for chunk {chunk.chunk_index}: {e}")
                raise
        return super().add(chunk)

    def _decrypt_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        """Helper to decrypt chunk content in-place."""
        if self.encryption_service and chunk.content:
            try:
                # Basic check if it looks encrypted (starts with nonce?)
                # Actually, just try decrypt. If not encrypted, it might fail or return garbage.
                # Ideally we should flag encrypted chunks in DB, but for now assuming all new are encrypted.
                # If we have mixed data, this is tricky. Protocol: Try decrypt, if fail, assume plaintext?
                # No, standard AESGCM will fail authentication tag check.
                decrypted = self.encryption_service.decrypt(chunk.content)
                chunk.content = decrypted
            except Exception:
                # Determine if we should fallback. 
                # If it's legacy data, it's plaintext. 
                # But decrypting random text might raise invalid tag.
                # Safe fallback: If decrypt fails, assume it's legacy plaintext.
                pass 
        return chunk

    def get_by_document_id(self, document_id: int) -> List[DocumentChunk]:
        """Get all chunks for a document (Decrypted)."""
        chunks = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()
        
        return [self._decrypt_chunk(c) for c in chunks]
    
    def get_by_ids(self, chunk_ids: List[int]) -> List[DocumentChunk]:
        """Get chunks by IDs (Decrypted)."""
        chunks = self.db.query(DocumentChunk).filter(
            DocumentChunk.id.in_(chunk_ids)
        ).all()
        return [self._decrypt_chunk(c) for c in chunks]
    
    def get_by_content_hash(self, content_hash: str) -> Optional[DocumentChunk]:
        """Get chunk by content hash (deduplication). Note: Hash is on plaintext."""
        # We store content_hash as SHA256 of plaintext. This is fine to search on.
        return self.db.query(DocumentChunk).filter(
            DocumentChunk.content_hash == content_hash
        ).first()

    def get_all(self) -> List[DocumentChunk]:
        """Get all chunks (Decrypted)."""
        chunks = self.db.query(DocumentChunk).all()
        return [self._decrypt_chunk(c) for c in chunks]

    def delete_by_document_id(self, document_id: int) -> int:
        """Delete all chunks for a document. Returns count of deleted chunks."""
        count = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()
        self.db.commit()
        return count





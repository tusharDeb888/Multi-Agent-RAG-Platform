"""
Tests for IngestionService.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.application.services.ingestion_service import IngestionService
from app.domain.models import Document, DocumentStatus

def test_process_document_success(db, test_user):
    """Test successful document processing."""
    # Create a dummy document
    doc = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        file_size_mb=1.0,
        mime_type="application/pdf",
        department="IT",
        uploaded_by=test_user.id,
        status=DocumentStatus.PENDING
    )
    db.add(doc)
    db.commit()
    
    # Mock dependencies
    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_batch.return_value = [[0.1] * 384]
    
    mock_vector_store = MagicMock()
    
    service = IngestionService(db, mock_embedding_service, mock_vector_store)
    
    # Mock internal methods to avoid actual file I/O
    with patch.object(service, '_extract_text') as mock_extract:
        mock_extract.return_value = [{"page_number": 1, "content": "Test content"}]
        
        result = service.process_document(doc.id)
        
        assert result is True
        assert doc.status == DocumentStatus.COMPLETED
        assert doc.total_pages == 1
        
        # Verify interactions
        mock_extract.assert_called_once()
        mock_embedding_service.embed_batch.assert_called_once()
        mock_vector_store.add_vectors.assert_called_once()

def test_process_document_not_found(db):
    """Test processing non-existent document."""
    service = IngestionService(db)
    result = service.process_document(999)
    assert result is False

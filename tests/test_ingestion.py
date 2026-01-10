"""
Tests for IngestionService.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.application.services.ingestion_service import IngestionService
from app.domain.models import Document, DocumentStatus

@pytest.mark.asyncio
async def test_process_document_success(db, test_user):
    """Test successful document processing."""
    # Create a dummy department if needed (db tables might be empty)
    # The models show Document can rely on Department/User
    
    # Create a dummy document
    doc = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        file_size_mb=1.0,
        mime_type="application/pdf",
        # department_id=1, # simplified
        uploaded_by=test_user.id,
        status=DocumentStatus.PENDING
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Mock dependencies
    mock_embedding_service = MagicMock()
    # Embed batch is run in thread, so it can be sync or wrapped. 
    # Ingestion service uses: await asyncio.to_thread(self.embeddings.embed_batch, texts)
    # So `embed_batch` should be a normal callable.
    mock_embedding_service.embed_batch.return_value = [[0.1] * 384]
    
    mock_vector_store = MagicMock()
    mock_vector_store.add_vectors = AsyncMock()
    mock_vector_store.save = AsyncMock()
    
    service = IngestionService(db, mock_embedding_service, mock_vector_store)
    
    # Mock strategy to avoid actual file extraction logic
    # We patch the triage and the stream generator effectively (or just the extractor used by stream)
    # _process_stream calls _triage_document (executor) and then _extract_text_fast_wrapper (executor)
    
    with patch.object(service, '_triage_document', return_value='FAST'), \
         patch.object(service, '_extract_text_fast_wrapper', return_value=[{"page_number": 1, "content": "Test content"}]), \
         patch("app.application.services.ingestion_service.os.path.exists", return_value=True): # For file check if any
        
        result = await service.process_document(doc.id)
        
        assert result is True
        
        # Reload doc
        db.refresh(doc)
        assert doc.status == DocumentStatus.SEARCHABLE
        
        # Verify interactions
        mock_embedding_service.embed_batch.assert_called()
        mock_vector_store.add_vectors.assert_called()

@pytest.mark.asyncio
async def test_process_document_not_found(db):
    """Test processing non-existent document."""
    service = IngestionService(db)
    result = await service.process_document(999)
    assert result is False

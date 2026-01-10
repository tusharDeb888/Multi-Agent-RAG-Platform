
import unittest
from dataclasses import dataclass
from typing import List
from app.application.services.rag_service import RAGService
from unittest.mock import MagicMock

# Mock classes
@dataclass
class MockDocument:
    filename: str

@dataclass
class MockChunk:
    id: int
    document_id: int
    page_number: int
    content: str
    document: MockDocument
    content_hash: str = "hash" 

class TestZeroTrustRAG(unittest.TestCase):
    def setUp(self):
        self.rag = RAGService(MagicMock()) # Mock DB session
        self.rag.settings = MagicMock()
        
    def test_dominant_locking_clear_winner(self):
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="A", document=MockDocument("A.pdf")),
            MockChunk(id=2, document_id=1, page_number=2, content="A", document=MockDocument("A.pdf")),
            MockChunk(id=3, document_id=2, page_number=1, content="B", document=MockDocument("B.pdf")),
        ]
        # Doc 1 Score: 10+10=20. Doc 2 Score: 5. Ratio: 5/20 = 0.25 (Safe)
        scores = [10.0, 10.0, 5.0]
        
        doc_id = self.rag._select_dominant_document(chunks, scores)
        self.assertEqual(doc_id, 1, "Should pick Doc 1 as clear winner")
        
    def test_dominant_locking_ambiguity(self):
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="A", document=MockDocument("A.pdf")),
            MockChunk(id=3, document_id=2, page_number=1, content="B", document=MockDocument("B.pdf")),
        ]
        # Doc 1: 10. Doc 2: 9. Ratio: 0.9 (>0.75) -> Ambiguous
        scores = [10.0, 9.0]
        
        doc_id = self.rag._select_dominant_document(chunks, scores)
        self.assertIsNone(doc_id, "Should return None for ambiguous documents")

    def test_deduplication(self):
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="Pump fails due to cavitation.", document=MockDocument("A.pdf"))
        ]
        # Answer has duplicates
        answer = "Pump fails due to cavitation [[1]]. The pump failure is caused by cavitation [[1]]."
        
        # We need to mock _extract_key_terms for semantic check
        self.rag._extract_key_terms = lambda x: {"pump", "cavitation"}
        
        validated = self.rag._validate_claims(answer, chunks)
        
        # Should drop second sentence
        self.assertEqual(validated, "Pump fails due to cavitation [[1]].")

    def test_claim_authorization_wrong_id(self):
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="Safe info.", document=MockDocument("A.pdf"))
        ]
        # Cited ID 999 is not in chunks (simulate unauthorized doc)
        answer = "Unauthorized secret [[999]]."
        
        validated = self.rag._validate_claims(answer, chunks)
        self.assertEqual(validated, "", "Should drop claim with unauthorized ID")

if __name__ == '__main__':
    unittest.main()

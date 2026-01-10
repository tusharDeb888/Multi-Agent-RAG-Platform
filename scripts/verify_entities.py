
import unittest
from typing import List, Dict, Optional
from app.application.services.rag_service import RAGService
from unittest.mock import MagicMock
from dataclasses import dataclass

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

class TestEntityGuardrail(unittest.TestCase):
    def setUp(self):
        self.rag = RAGService(MagicMock())
        self.rag.settings = MagicMock()
        
    def test_entity_extraction(self):
        # Alice is a proper noun.
        query = "Tell me about Alice."
        entities = self.rag._extract_query_entities(query)
        self.assertIn("Alice", entities)
        
        # "Tell" is a stopword at start, should be ignored.
        self.assertNotIn("Tell", entities)
        
        # "Zomato Limited" -> Zomato, Limited
        query2 = "Does Zomato Limited have a policy?"
        entities2 = self.rag._extract_query_entities(query2)
        self.assertIn("Zomato", entities2)
        self.assertIn("Limited", entities2)

    def test_guardrail_fail(self):
        query = "Where is Alice?" # Entity: Alice
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="The project manager is Bob.", document=MockDocument("doc.pdf"))
        ]
        # "Alice" not in "The project manager is Bob."
        result = self.rag._enforce_entity_presence(query, chunks)
        self.assertFalse(result, "Should fail because Alice is missing")

    def test_guardrail_pass(self):
        query = "Where is Bob?" # Entity: Bob
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="The project manager is Bob.", document=MockDocument("doc.pdf"))
        ]
        # "Bob" is present
        result = self.rag._enforce_entity_presence(query, chunks)
        self.assertTrue(result, "Should pass because Bob is present")
        
    def test_guardrail_pass_no_entities(self):
        query = "what is the status?" # No capitalized proper nouns (swc)
        chunks = [
            MockChunk(id=1, document_id=1, page_number=1, content="Status is green.", document=MockDocument("doc.pdf"))
        ]
        result = self.rag._enforce_entity_presence(query, chunks)
        self.assertTrue(result, "Should pass if no entities in query")

if __name__ == '__main__':
    unittest.main()

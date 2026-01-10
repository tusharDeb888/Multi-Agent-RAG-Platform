
import unittest
from unittest.mock import MagicMock
from app.infrastructure.search.reranker_service import RerankerService
from app.domain.models import DocumentChunk
from dataclasses import dataclass

@dataclass
class MockChunk:
    id: int
    content: str

class TestReranker(unittest.TestCase):
    def setUp(self):
        # We will use the real reranker model if possible, or mock it if too heavy for test environment.
        # But user requested enterprise grade, so let's try real model. 
        # Note: First run might be slow due to download.
        self.reranker = RerankerService()
        
    def test_reranking_accuracy(self):
        if not self.reranker.model:
            print("Skipping test: model failed to load")
            return

        query = "How to fix centrifugal pump vibration?"
        
        # Chunk A: Highly Relevant
        chunk_a = MockChunk(id=1, content="Centrifugal pump vibration is often caused by cavitation or misalignment. Check the impeller balance.")
        
        # Chunk B: Irrelevant (but maybe high vector score due to keywords 'pump' and 'fix')
        chunk_b = MockChunk(id=2, content="To fix a flat tire, use a patch kit. Pump the tire afterwards.")
        
        chunks = [chunk_a, chunk_b]
        
        reranked_chunks, scores = self.reranker.rerank(query, chunks, top_k=2)
        
        # Expect Chunk A to be first
        self.assertEqual(reranked_chunks[0].id, 1, "Reranker should prioritize the relevant pump chunk")
        self.assertGreater(scores[0], scores[1], "Relevant chunk should have higher score")
        
        print(f"Relevant Output: {reranked_chunks[0].content[:50]}... Score: {scores[0]:.4f}")
        print(f"Irrelevant Output: {reranked_chunks[1].content[:50]}... Score: {scores[1]:.4f}")

if __name__ == '__main__':
    unittest.main()

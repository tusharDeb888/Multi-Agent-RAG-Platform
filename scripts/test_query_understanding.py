
import unittest
import asyncio
from unittest.mock import MagicMock
from app.application.services.rag_service import RAGService
from app.infrastructure.llm.base import LLMRequest, LLMResponse

class TestQueryUnderstanding(unittest.TestCase):
    def setUp(self):
        self.mock_llm = MagicMock()
        self.rag = RAGService(MagicMock(), llm_adapter=self.mock_llm)
        self.rag.settings = MagicMock()
        
    def test_analyze_query_executive(self):
        # Mock LLM response for analysis
        json_resp = '{"intent": "Summary", "tone": "Executive", "keywords": ["pump"], "is_ambiguous": false}'
        self.mock_llm.generate.return_value = LLMResponse(text=json_resp, tokens_used=50, model_name="mock")
        
        # Run
        meta = asyncio.run(self.rag._analyze_query("Summarize pump status for the CEO"))
        
        self.assertEqual(meta["intent"], "Summary")
        self.assertEqual(meta["tone"], "Executive")
        
    def test_retry_generation(self):
        # Mock LLM response for retry
        self.mock_llm.generate.return_value = LLMResponse(text="Cited answer [[1]]", tokens_used=100)
        
        # Run
        new_answer = asyncio.run(self.rag._retry_generation_with_correction("query", "context", "bad answer"))
        
        self.assertEqual(new_answer, "Cited answer [[1]]")
        # Verify prompt contained "FAILURE REPORT"
        last_call = self.mock_llm.generate.call_args[0][0]
        self.assertIn("FAILURE REPORT", last_call.prompt)

if __name__ == '__main__':
    unittest.main()

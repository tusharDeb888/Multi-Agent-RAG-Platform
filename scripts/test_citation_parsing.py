
import re
import unittest
from dataclasses import dataclass
from typing import List, Dict, Optional

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

class TestCitationNormalization(unittest.TestCase):
    def _normalize_citations(self, text: str, citations: List[Dict]) -> tuple[str, List[Dict]]:
        """Mock implementation of the normalization logic logic added to RAGService"""
        if not citations:
            return text, []

        matches = list(re.finditer(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', text, re.IGNORECASE))
        
        chunk_appearance_order = []
        seen_chunks = set()
        
        for m in matches:
            cid = int(m.group(2))
            if cid not in seen_chunks:
                chunk_appearance_order.append(cid)
                seen_chunks.add(cid)
                
        doc_map = {c['chunk_id']: c for c in citations}
        for c in citations:
            if c['chunk_id'] not in seen_chunks:
                 chunk_appearance_order.append(c['chunk_id'])
                 
        id_to_index = {cid: i+1 for i, cid in enumerate(chunk_appearance_order)}
        
        def replace_match(match):
            cid = int(match.group(2))
            if cid in id_to_index:
                return f"[{id_to_index[cid]}]"
            return match.group(0)
            
        normalized_text = re.sub(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', replace_match, text, flags=re.IGNORECASE)
        
        ordered_citations = []
        for cid in chunk_appearance_order:
            if cid in doc_map:
                cit = doc_map[cid]
                cit['index'] = id_to_index[cid] 
                ordered_citations.append(cit)
                
        return normalized_text, ordered_citations

    def test_normalization(self):
        text = "Pump failure [[101]] is common. Also checks safety [[201]] and docs [[DOC 101]]."
        citations = [
            {'chunk_id': 101, 'document_name': 'Pump.pdf'},
            {'chunk_id': 201, 'document_name': 'Safety.pdf'}
        ]
        
        norm_text, norm_cits = self._normalize_citations(text, citations)
        
        # Expectation: 
        # 101 appears first -> [1]
        # 201 appears second -> [2]
        # Text: "Pump failure [1] is common. Also checks safety [2] and docs [1]."
        
        expected_text = "Pump failure [1] is common. Also checks safety [2] and docs [1]."
        self.assertEqual(norm_text, expected_text)
        
        self.assertEqual(len(norm_cits), 2)
        self.assertEqual(norm_cits[0]['chunk_id'], 101)
        self.assertEqual(norm_cits[0]['index'], 1)
        self.assertEqual(norm_cits[1]['chunk_id'], 201)
        self.assertEqual(norm_cits[1]['index'], 2)

if __name__ == '__main__':
    unittest.main()

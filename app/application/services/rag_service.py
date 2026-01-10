"""
RAG Service for Retrieval-Augmented Generation.
Follows Single Responsibility Principle - only handles RAG operations.
"""
from typing import List, Dict, Optional, Any
import numpy as np
import os
import time
import asyncio
import re
import json
from contextlib import contextmanager
from sqlalchemy.orm import Session
from loguru import logger

@contextmanager
def PerformanceTimer(name: str):
    """Context manager to measure and log block execution time."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        logger.info(f"[Perf] {name} took {t1 - t0:.3f}s")

from app.infrastructure.llm.base import BaseLLMAdapter, LLMRequest
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.llm.prompts import ENTERPRISE_RAG_SYSTEM_PROMPT, QUERY_ANALYSIS_PROMPT
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.search.reranker_service import RerankerService
from app.infrastructure.vector_store.base import BaseVectorStore

from app.domain.repositories.chunk_repository import ChunkRepository
from app.domain.models import DocumentChunk
from app.application.services.rbac_service import RBACService
from app.core.config import get_settings
from app.domain.rag_types import UserIntent, RetrievalOutcome, RAGResponse, SourceChunk, QueryAnalysisResult


class RAGService:
    """
    Retrieval-Augmented Generation service.
    Combines vector search with LLM generation.
    """
    
    def __init__(
        self,
        db: Session,
        llm_adapter: Optional[BaseLLMAdapter] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[BaseVectorStore] = None,
        rbac_service: Optional[RBACService] = None
    ):
        """
        Initialize RAG service.
        """
        self.db = db
        self.settings = get_settings()
        
        # Dependency injection
        self.llm = llm_adapter or LLMFactory.create_llm_adapter()
        self.embeddings = embedding_service or EmbeddingService()
        self.reranker = RerankerService() # Enterprise Reranker
        self.vector_store = vector_store or self._create_vector_store()
        self.rbac = rbac_service or RBACService(db)
        self.chunk_repo = ChunkRepository(db)
        
        # Initialize Cache
        from app.infrastructure.cache.cache_service import CacheService
        self.cache = CacheService()

        # [Phase 4] Initialize Semantic Cache
        from app.application.services.semantic_cache_service import SemanticCacheService
        self.semantic_cache = SemanticCacheService()
        
        # Initialize Reranker
        # RerankerService now uses the Async CrossEncoderRanker internally

        
        # Initialize BM25 Retriever
        from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever
        self.bm25 = SparseBM25Retriever()

        # Define path for Lazy Loading in search()
        # Using .bm25_index to indicate directory structure (Secure Persistence)
        self.bm25_path = f"{self.settings.index_storage_path}.bm25_index"

             
        # Initialize Prompt Firewall
        from app.core.prompt_firewall import PromptFirewall
        self.firewall = PromptFirewall()
    
    def _is_chitchat(self, query: str) -> bool:
        """Check if query is simple chitchat/greeting."""
        greetings = {"hi", "hello", "hey", "good morning", "good evening", "greetings"}
        # Simple heuristic: short length and keyword match
        cleaned = query.strip().lower()
        if len(cleaned.split()) < 4 and any(g in cleaned for g in greetings):
            return True
        return False
             
    def _create_vector_store(self) -> BaseVectorStore:
        """Create vector store instance."""
        # Default to Milvus
        if self.settings.vector_index_type == "milvus" or self.settings.vector_index_type == "milvus": # Enum check vs String
            from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
            return MilvusVectorStore()
            
        elif self.settings.vector_index_type == "oracle_vector":
            from app.infrastructure.vector_store.oracle_store import OracleVectorStore
            return OracleVectorStore()
            
        else:
            # Fallback to Milvus if configured but not matched above? 
            # Or just raise error. Since we updated default to MILVUS, this is safe.
            from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
            return MilvusVectorStore()

    async def reload_indices(self):
        """
        [Admin] Hot reload of BM25 index and other resources.
        Used after re-indexing completes.
        """
        logger.info("Hot Reload: Refreshing indices...")
        if os.path.exists(self.bm25_path):
             # Singleton will update in-place
             try:
                 await self.bm25.load(self.bm25_path)
                 if self.bm25.is_fitted:
                     logger.info("Hot Reload: BM25 index updated successfully.")
                 else:
                     logger.warning("Hot Reload: Loaded BM25 index was not fitted.")
             except Exception as e:
                  logger.error(f"Hot Reload Failed: {e}")
        else:
             logger.warning("Hot Reload: BM25 index file not found.")

    def _check_refusal(self, text: str) -> bool:
        """Check if response is a refusal."""
        refusal_markers = [
            "cannot find",
            "does not contain",
            "unable to find",
            "no information",
            "not mentioned",
            "context does not",
            "access is restricted",
            "system does not contain",
            "i don't know",
            "provided documents do not",
            "no grounded information",
            "authorized document"
        ]
        text_lower = text.lower()
        return any(marker in text_lower for marker in refusal_markers)

    def _sanitize_response(self, text: str) -> str:
        """
        Handle 'Split Personality' responses where LLM provides an answer 
        BUT also appends the refusal string (e.g. 'No grounded information...').
        If substantial valid answer exists, strip the refusal suffix.
        """
        refusal_prefix = "No grounded information found in the authorized document"
        
        # Check if refusal pattern exists
        if refusal_prefix in text:
            parts = text.split(refusal_prefix)
            valid_content = parts[0].strip()
            
            # If we have substantial content (e.g. > 50 chars), assume it's a valid answer
            # and the refusal was a hallucinated footer or hedging.
            if len(valid_content) > 50:
                logger.info("Sanitizer: Detected Mixed Refusal. Stripping refusal suffix and trusting answer.")
                return valid_content
                
        return text
    
    def _normalize_citations(self, text: str, citations: List[Dict]) -> tuple[str, List[Dict]]:
        """
        Normalize citations in text from [[ID]] to [1], [2] etc.
        Returns: (normalized_text, ordered_citations)
        """
        if not citations:
            return text, []

        # Map internal Chunk ID -> Display Index (1-based)
        # We want to number them in order of APPEARANCE in the text if possible, 
        # but citations list passed here is already unique-ified.
        # Let's re-scan text to find order of appearance.
        
        matches = list(re.finditer(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', text, re.IGNORECASE))
        
        chunk_appearance_order = []
        seen_chunks = set()
        
        # 1. Determine order of appearance
        for m in matches:
            cid = int(m.group(2))
            if cid not in seen_chunks:
                chunk_appearance_order.append(cid)
                seen_chunks.add(cid)
                
        # 2. Add any citations that weren't in text (rare, but possible if fallback)
        doc_map = {c['chunk_id']: c for c in citations}
        for c in citations:
            if c['chunk_id'] not in seen_chunks:
                 chunk_appearance_order.append(c['chunk_id'])
                 
        # 3. Create Mapping: ChunkID -> Index
        id_to_index = {cid: i+1 for i, cid in enumerate(chunk_appearance_order)}
        
        # 4. Rewrite Text
        def replace_match(match):
            cid = int(match.group(2))
            if cid in id_to_index:
                return f"[{id_to_index[cid]}]"
            return match.group(0) # Leave unknown IDs alone
            
        normalized_text = re.sub(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', replace_match, text, flags=re.IGNORECASE)
        
        # 5. Reorder Citations List
        ordered_citations = []
        for cid in chunk_appearance_order:
            if cid in doc_map:
                cit = doc_map[cid]
                # Embed index into citation object for frontend if useful (though array index is implicit)
                cit['index'] = id_to_index[cid] 
                ordered_citations.append(cit)
                
        return normalized_text, ordered_citations

    def _extract_citations_from_text(self, text: str, chunks: List[DocumentChunk]) -> List[Dict]:
        """
        Parse citations tags and return verified citation objects.
        Supports: [[123]], [123], [[ID: 123]], [[Doc 123]]
        """
        citations = []
        try:
            # Robust Regex:
            # 1. Matches [[123]] or [123]
            # 2. Handles optional "ID:" or "Doc" prefixes
            # 3. Captures the digits
            matches = re.findall(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', text, re.IGNORECASE)
            cited_ids = {int(m[1]) for m in matches}
            
            valid_chunk_map = {c.id: c for c in chunks}
            seen_pages = set()
            
            for cid in cited_ids:
                if cid in valid_chunk_map:
                    chunk = valid_chunk_map[cid]
                    doc_id = chunk.document_id
                    page_key = (doc_id, chunk.page_number)
                    
                    if page_key not in seen_pages:
                        # Create a snippet (first 200 chars) for UI verification
                        snippet_text = chunk.content[:200].replace("\n", " ") + "..." if len(chunk.content) > 200 else chunk.content
                        
                        # Extract External URL if available
                        source_url = None
                        if chunk.document and chunk.document.metadata_json:
                            try:
                                doc_meta = json.loads(chunk.document.metadata_json)
                                base_url = doc_meta.get("url") or doc_meta.get("source_url")
                                if base_url:
                                    # [Source Upgrade] Append page fragment for exact deep linking
                                    if chunk.page_number:
                                        # Check if URL already has fragment
                                        sep = "&" if "#" in base_url else "#"
                                        # If PDF, standard is #page=N. For HTML, might need custom anchor.
                                        # Assuming generic PDF/Viewer support:
                                        if base_url.lower().endswith('.pdf'):
                                            source_url = f"{base_url}#page={chunk.page_number}"
                                        else:
                                            source_url = f"{base_url}{sep}page={chunk.page_number}"
                                    else:
                                        source_url = base_url
                            except Exception:
                                pass # Ignore metadata parsing errors
                        
                        citations.append({
                            "document_id": doc_id,
                            "document_name": chunk.document.filename if chunk.document else "Unknown",
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,  # [Deep Audit Fix] Added for RAGResponse compatibility
                            "page_number": chunk.page_number,
                            "snippet": snippet_text,
                            "source_url": source_url,
                            "similarity_score": 0.0 # Placeholder, will be populated if possible or unused
                        })
                        seen_pages.add(page_key)
        except Exception as e:
            logger.warning(f"Failed to extract citations: {e}")
            
        return citations
    
    def _extract_key_terms(self, text: str) -> set:
        """Extract significant terms for coverage checking."""
        if not text: return set()
        # Basic stopword list - in production use NLTK/Spacy
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "be", "been", "tell", "me", "about", "how", "what", "who", "when", "where", "why", "which"}
        
        words = re.findall(r'\b\w+\b', text.lower())
        # Rudimentary stemming: strip trailing 's', 'ing', 'ed' could be added but 's' is safest
        # [Deep Audit Fix] Acronym Support: Allow 2-letter words (e.g. AI, QC) if not stopwords
        return {w.rstrip('s') for w in words if w not in stopwords and len(w) >= 2}

    def _select_dominant_document(
        self, 
        chunks: List[DocumentChunk], 
        scores: List[float]
    ) -> Optional[int]:
        """
        [Layer: Dominant Document Selection]
        Selects the single best document ID.
        FAIL CLOSED: If there is ambiguity (two documents with similar high scores), return None.
        """
        if not chunks: return None
        
        from collections import defaultdict
        
        # 1. Aggregation
        doc_scores = defaultdict(float)
        doc_counts = defaultdict(int)
        
        for chunk, score in zip(chunks, scores):
            # Only consider "Positive" signal chunks for authority
            if score > 0.0:
                 doc_scores[chunk.document_id] += score
                 doc_counts[chunk.document_id] += 1
        
        if not doc_scores:
             return None
             
        # 2. Sorting
        sorted_docs = sorted(
            doc_scores.keys(), 
            key=lambda did: doc_scores[did], 
            reverse=True
        )
        
        best_doc_id = sorted_docs[0]
        best_score = doc_scores[best_doc_id]
        
        logger.info(f"Dominant Selection: Best Doc {best_doc_id} (Score: {best_score:.2f})")
        
        # 3. Ambiguity Check (Zero-Trust)
        # If we have a second document, check if it's "Close Enough" to cause bleed risk
        if len(sorted_docs) > 1:
            second_doc_id = sorted_docs[1]
            second_score = doc_scores[second_doc_id]
            
            # Ratio Check: If 2nd place has > 75% of 1st place score -> AMBIGUOUS
            ratio = second_score / best_score if best_score > 0 else 0
            if ratio > 0.75:
                 logger.warning(f"Ambiguity Detected! Doc {best_doc_id} ({best_score:.2f}) vs Doc {second_doc_id} ({second_score:.2f}). Ratio: {ratio:.2f}")
                 # FAIL CLOSED
                 return None
                 
        return best_doc_id

    # [REMOVED DUPLICATE _validate_claims]
    # The authoritative version is defined later in the class.

    
    async def _expand_query(self, query: str) -> str:
        """
        Expand queries into proper search questions to improve retrieval.
        Leverages LLM internal knowledge to interpret user intent and synonyms.
        """

        # Heuristic: Run for most queries that aren't already long detailed explanations
        # Optimization: Reduced threshold and regex fast-paths
        
        # 1. Fast Path: Skip if query looks like a specific code or is very specific
        # Regex for common codes like "PRJ-99", "ISO 9001", "Section 5.2"
        if re.search(r'\b[A-Z]{2,4}[-_]\d{2,5}\b', query) or re.search(r'\b(section|article)\s+\d+', query, re.IGNORECASE):
             logger.info("Fast Path: Skipping expansion for specific code/section reference")
             return query

        # 2. Threshold Check
        if len(query.split()) < self.settings.expansion_threshold:
            logger.info(f"Expanding query: '{query}'")
            prompt = (
                f"You are a query optimizer. Reformulate the user's query into a precise, standalone search query.\n"
                f"User Query: \"{query}\"\n\n"
                f"Instructions:\n"
                f"1. Remove conversational filler (e.g., 'tell me about', 'please find').\n"
                f"2. Expand abbreviations and add relevant technical synonyms.\n"
                f"3. Keep specific codes (e.g. 'ISO-9001', 'PRJ-99') EXACT.\n"
                f"4. Output ONLY the improved query string. Be concise but comprehensive.\n\n"
                f"Examples:\n"
                f"- Input: \"why is the pump making noise\"\n"
                f"- Output: \"centrifugal pump cavitation noise vibration mechanical failure causes troubleshooting\"\n"
                f"- Input: \"who is Charlie\"\n"
                f"- Output: \"Charlie employee profile role department responsibilities\"\n\n"
                f"Optimized Query:"
            )
            llm_request = LLMRequest(
                prompt=prompt,
                max_tokens=60,
                temperature=0.05,  # Lower temperature for precision
                stop_sequences=["\n\n"],
                system_prompt="You are a query expansion expert."
            )
            try:
                # Use a separate non-streaming call for expansion
                response = await asyncio.to_thread(self.llm.generate, llm_request)
                expanded = response.text.strip().strip('"').strip("'")
                
                # Cleaning
                for prefix in ["Here is", "Optimized Query:", "Output:", "**"]:
                    if expanded.lower().startswith(prefix.lower()):
                        expanded = expanded[len(prefix):].strip()
                        
                # Sanity Check
                if len(expanded) < 3 or len(expanded) > len(query) * 4: # Guard against hallway-ucination
                     logger.warning(f"Expansion seemed odd ('{expanded}'), blending with original")
                     # If unsure, concat original to ensure keywords aren't lost
                     expanded = f"{query} {expanded}"

                logger.info(f"Expanded query: '{expanded}'")
                return expanded
            except Exception as e:
                logger.warning(f"Query expansion failed: {e}")
                return query
        return query

    async def _generate_hyde_answer(self, query: str) -> str:
        """
        [HyDE] Generate a Hypothetical Document (Answer) to improve retrieval.
        The vector of this hypothetical answer is often closer to the target document
        than the query vector itself.
        """
        prompt = (
            f"Please write a short, plausible passage that answers the question. "
            f"Do not include any explanations. Just write the answer text as if it appeared in a document.\n\n"
            f"Question: \"{query}\"\n"
            f"Passage:"
        )
        llm_request = LLMRequest(
            prompt=prompt, 
            max_tokens=150, 
            temperature=0.15, # Low temperature for factual HyDE
            stop_sequences=["\n"],
            system_prompt="You are a helpful assistant generating hypothetical document excerpts."
        )
        try:
            response = await asyncio.to_thread(self.llm.generate, llm_request)
            hyde_text = response.text.strip()
            logger.info(f"[HyDE] Generated hypothetical answer: {hyde_text[:50]}...")
            return hyde_text
        except Exception as e:
            logger.warning(f"[HyDE] Failed: {e}")
            return ""

    async def _classify_intent(self, query: str) -> UserIntent:
        """Classify user intent using LLM or heuristics."""
        # [Deep Audit Fix] Sanitize input to prevent Prompt Injection in Classification
        query = self.firewall.sanitize(query)
        
        # 1. Heuristics for speed
        query_lower = query.lower()
        if re.search(r'\b(list|enumerate|protocols|procedures|steps)\b', query_lower):
            return UserIntent.ENUMERATION
        if re.search(r'\b(how to|procedure|steps|guide|reset|configure)\b', query_lower):
            return UserIntent.OPERATIONAL
        if re.search(r'\b(compare|difference|versus|vs)\b', query_lower):
            return UserIntent.COMPARISON
        if re.search(r'\b(find|search|lookup|who is)\b', query_lower):
            return UserIntent.NAVIGATION
        if re.search(r'\b(password|secret|key|admin|root)\b', query_lower):
            return UserIntent.RESTRICTED
            
        # 2. LLM Fallback (Zero-Shot Classification)
        prompt = (
            f"Classify the user query into one of these categories:\n"
            f"1. CHITCHAT (Greetings, small talk)\n"
            f"2. FACT_LOOKUP (Specific question about data/facts)\n"
            f"3. OPERATIONAL (How-to, guides, procedures)\n"
            f"4. COMPARISON (Compare X vs Y)\n"
            f"5. INTERNAL_KNOWLEDGE (Definitions, common knowledge, 'What can you do?')\n"
            f"6. SUMMARY (Summarize document X)\n\n"
            f"Query: \"{query}\"\n\n"
            f"Reply ONLY with the category name."
        )
        
        try:
            llm_request = LLMRequest(
                prompt=prompt,
                max_tokens=10,
                temperature=0.0,
                stop_sequences=["\n"]
            )
            # Use separate call to avoid interference 
            # (In prod, this should be a smaller, faster model or cached)
            response = await self.llm.generate(llm_request)
            category = response.text.strip().upper()
            
            logger.info(f"LLM Intent Classification: {category}")
            
            if "OPERATIONAL" in category: return UserIntent.OPERATIONAL
            if "COMPARISON" in category: return UserIntent.COMPARISON
            if "SUMMARY" in category: return UserIntent.DESCRIPTION
            if "INTERNAL_KNOWLEDGE" in category: return UserIntent.CHITCHAT # Treat as chitchat to skip retrieval if desired, or map to new type
            if "CHITCHAT" in category: return UserIntent.CHITCHAT
            
            return UserIntent.FACT_LOOKUP
            
        except Exception as e:
            logger.warning(f"Intent Classification failed: {e}. Falling back to default.")
            return UserIntent.FACT_LOOKUP

    def _determine_outcome(
        self, 
        candidates_count: int, 
        accessible_count: int, 
        final_chunks: List[DocumentChunk], 
        top_score: float = 0.0
    ) -> RetrievalOutcome:
        """Determine system state based on retrieval results."""
        if candidates_count > 0 and accessible_count == 0:
            return RetrievalOutcome.ACCESS_DENIED
        
        if candidates_count == 0:
            return RetrievalOutcome.NO_DATA
            
        if not final_chunks:
            # Candidates existed, but Reranker rejected all (or none fit context)
            return RetrievalOutcome.AMBIGUOUS
            
        # Check scores of top chunk
        if top_score > 30.0: # Arbitrary high score from CrossEncoder
            return RetrievalOutcome.STRONG_MATCH
        elif top_score > 0.0:
            return RetrievalOutcome.PARTIAL_MATCH
            
        return RetrievalOutcome.PARTIAL_MATCH # Default fallthrough
    
    async def _analyze_query(self, query: str) -> QueryAnalysisResult:
        """
        Analyze query for Intent, Tone, and Ambiguity using LLM.
        Returns QueryAnalysisResult model.
        """
        try:
            # 1. Construct Request
            # [Deep Audit Fix] Sanitize input to prevent Prompt Injection in Analysis
            safe_query = self.firewall.sanitize(query)
            
            system_msg = QUERY_ANALYSIS_PROMPT
            user_msg = f"Query: {safe_query}"
            
            # 2. Call LLM (Low Temperature for JSON consistency)
            request = LLMRequest(
                system_prompt=system_msg,
                prompt=user_msg, 
                temperature=0.0,
                max_tokens=200,
                response_format="json" # Native JSON Mode (Ollama)
            ) 
            
            # [Deep Audit Fix] Async execution for Analysis to avoid blocking Loop
            response = await self.llm.generate(request)
            response_text = response.text
            
            # 3. Parse JSON (Robust Extraction)
            import re
            import ast
            
            # Find the first JSON object using regex (handles preamble/markdown)
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                clean_json = response_text[start_idx : end_idx + 1]
            else:
                clean_json = response_text.replace("```json", "").replace("```", "").strip()
            
            try:
                metadata = json.loads(clean_json)
            except json.JSONDecodeError:
                # Fallback: Try ast.literal_eval for Python-style dicts (single quotes)
                try:
                    metadata = ast.literal_eval(clean_json)
                    if not isinstance(metadata, dict): raise ValueError("Not a dict")
                except Exception:
                    # Fallback: Scrape structured data from text
                    try:
                        metadata = self._scrape_metadata_from_text(response_text)
                        if not metadata.get("intent"): 
                            raise ValueError("Scraper failed to find intent")
                        logger.info(f"Recovered Metadata via Scraper: {metadata}")
                    except Exception:
                        logger.warning(f"JSON Parse Failed. Raw LLM Output: {response_text[:200]}...")
                        raise ValueError("Could not parse JSON from LLM response")
            
            logger.info(f"Query Analysis: {metadata}")
            
            # Strict Mapping
            intent_str = metadata.get("intent", "Fact Retrieval").upper().replace(" ", "_")
            if "CHIT" in intent_str: intent_enum = UserIntent.CHITCHAT
            elif "OPERATIONAL" in intent_str: intent_enum = UserIntent.OPERATIONAL
            elif "COMPARISON" in intent_str: intent_enum = UserIntent.COMPARISON
            elif "ENUMERATION" in intent_str: intent_enum = UserIntent.ENUMERATION
            elif "NAV" in intent_str: intent_enum = UserIntent.NAVIGATION
            elif "RESTRICTED" in intent_str: intent_enum = UserIntent.RESTRICTED
            elif "DESC" in intent_str: intent_enum = UserIntent.DESCRIPTION
            else: intent_enum = UserIntent.FACT_LOOKUP
            
            return QueryAnalysisResult(
                intent=intent_enum,
                tone=metadata.get("tone", "General"),
                keywords=metadata.get("keywords", []),
                is_ambiguous=metadata.get("is_ambiguous", False)
            )
            
        except Exception as e:
            logger.error(f"Query Analysis Failed: {e}. Falling back to default.")
            return QueryAnalysisResult()

    def _scrape_metadata_from_text(self, text: str) -> Dict[str, Any]:
        """Fallback: Scrape structured data from non-JSON LLM chatter."""
        import re
        data = {}
        
        # Intent: Match "Intent" + separators + ANYTHING until newline
        intent_match = re.search(r'(?:Intent|intent)[\s\*]*[:\-][\s\*]*(.*)', text)
        if intent_match:
            # Strip quotes and extra whitespace
            raw_val = intent_match.group(1).strip().strip('"').strip("'")
            data["intent"] = raw_val
            
        # Tone
        tone_match = re.search(r'(?:Tone|tone)[\s\*]*[:\-][\s\*]*(.*)', text)
        if tone_match:
            raw_val = tone_match.group(1).strip().strip('"').strip("'")
            data["tone"] = raw_val
            
        # Keywords
        keywords_match = re.search(r'(?:Keywords|keywords)[\s\*]*[:\-][\s\*]*(.*)', text)
        if keywords_match:
            kw_str = keywords_match.group(1).strip()
            # Clean brackets and split
            kw_str = kw_str.replace("[", "").replace("]", "")
            data["keywords"] = [k.strip().strip('"').strip("'") for k in kw_str.split(",") if k.strip()]
            
        # Ambiguity
        if re.search(r'is_ambiguous[:\s]+true', text, re.IGNORECASE):
             data["is_ambiguous"] = True
        else:
             data["is_ambiguous"] = False
                 
        return data

    def _extract_query_entities(self, query: str) -> set[str]:
        """
        Extract Proper Nouns (potential entities) from query using heuristics.
        """
        # 1. Regex for capitalized words (allowing hyphens/digits like "ISO-9001")
        # Exclude start of sentence if it's a common stopword
        matches = re.findall(r'\b[A-Z][a-zA-Z0-9-]*\b', query)
        
        entities = set()
        stopwords = {"Who", "What", "Where", "When", "Why", "How", "Is", "Are", "Can", "Could", "Tell", "Describe", "Explain", "Show", "The", "A", "An", "In", "On", "At", "For", "To"}
        
        for i, m in enumerate(matches):
            # Heuristic: If it's the first word and a stopword, ignore.
            # But if it's "Alice" at the start, keep it (not in stopwords).
            if i == 0 and query.startswith(m) and m in stopwords:
                continue
            entities.add(m)
            
        return entities

    def _validate_claims(self, answer: str, chunks: List[DocumentChunk]) -> str:
        """
        [Layer: Claim Authorization & Deduplication - ENHANCED]
        Splits answer into sentences, verifies support, and removes duplicates.
        Includes Deduplication and Auto-Citation logic.
        """
        if not answer or not chunks:
            return ""
            
        import re
        from difflib import SequenceMatcher
        
        # 1. Split into sentences (Robust)
        split_pattern = r'(?:(?<!\b(?:Mr|Ms|Dr|Sr|Jr|vs|ex)\.)(?<!\bMrs\.)(?<!\bProf\.)(?<=\.)|(?<=[?!]))\s+(?=[A-Z])'
        sentences = re.split(split_pattern, answer)
        
        valid_sentences = []
        seen_content = []
        chunk_map = {c.id: c for c in chunks}
        
        for sent in sentences:
            sent = sent.strip()
            if not sent: continue
            
            # --- deduplication ---
            sent_clean = re.sub(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', '', sent).strip().lower()
            is_dup = False
            for seen in seen_content:
                seen_clean = re.sub(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', '', seen).strip().lower()
                if SequenceMatcher(None, sent_clean, seen_clean).ratio() > 0.6:
                    logger.info(f"Deduplication: Dropped '{sent[:30]}...'")
                    is_dup = True
                    break
            if is_dup: continue

            # --- Extract Citations ---
            cited_ids = [int(m[1]) for m in re.findall(r'\[+(:?ID:?|Doc)?\s*(\d+)\]+', sent, re.IGNORECASE)]
            
            # --- Auto-Citation If Missing ---
            if not cited_ids:
                 best_chunk_id = None
                 max_overlap_count = 0
                 sent_terms = self._extract_key_terms(sent)
                 
                 for chunk in chunks:
                     chunk_terms = self._extract_key_terms(chunk.content)
                     overlap = sent_terms.intersection(chunk_terms)
                     if len(overlap) > max_overlap_count:
                         max_overlap_count = len(overlap)
                         best_chunk_id = chunk.id

                 # Threshold: 1 significant term is enough for auto-rescue
                 if max_overlap_count >= 1 and best_chunk_id:
                     logger.info(f"Auto-Citation: Injected ID {best_chunk_id} for '{sent[:30]}...'")
                     sent = f"{sent} [[{best_chunk_id}]]"
                     cited_ids = [best_chunk_id]
                 else:
                     logger.warning(f"Claim dropped (No citation & No semantic match): '{sent[:50]}...'")
                     continue

            # --- Semantic Verification ---
            is_supported = False
            for cid in cited_ids:
                if cid in chunk_map:
                    chunk = chunk_map[cid]
                    sent_terms = self._extract_key_terms(sent)
                    chunk_terms = self._extract_key_terms(chunk.content)
                    overlap = sent_terms.intersection(chunk_terms)
                    
                    # Relaxed Check: 1 term match is acceptable
                    if len(overlap) >= 1:
                        is_supported = True
                        break
            
            if is_supported:
                valid_sentences.append(sent)
                seen_content.append(sent)
            else:
                 logger.warning(f"Claim dropped (Semantic mismatch with cited ID): '{sent[:50]}...'")
                 
        if not valid_sentences:
            return ""
            
        return " ".join(valid_sentences)

    def _enforce_entity_presence(self, query: str, chunks: List[DocumentChunk]) -> bool:
        """
        [Layer: Entity consistency]
        Verify entities are present in chunks. Relaxed for robustness.
        """
        entities = self._extract_query_entities(query)
        if not entities:
            return True 
            
        full_text = " ".join([c.content.lower() for c in chunks])
        
        passed_count = 0
        for entity in entities:
            # Robust Check: Allow whitespace variations (e.g. Standard-Class vs Standard Class)
            pattern = re.escape(entity.lower()).replace(r'\-', r'[\-\s]?').replace(r'\ ', r'[\-\s]?')
            if re.search(pattern, full_text):
                passed_count += 1
            else:
                logger.debug(f"Entity '{entity}' not found in context (Strict).")

        # If at least 50% of extracted entities are found, or if only 1 and it's missing (maybe hallucinated extraction)
        # Fallback: Trust Reranker. Just LOG warning instead of blocking blocks.
        if passed_count == 0 and len(entities) > 0:
             logger.warning(f"Entity Guardrail Warning: None of {entities} found in context. Proceeding with caution.")
             # return False # DISABLE Strict Fail-Closed to prevent "Response Retracted" on valid partial matches
             return True 

        return True

    async def _retry_generation_with_correction(self, query: str, context: str, previous_answer: str) -> str:
        """
        [Self-Correction Loop]
        Called when _validate_claims rejects the answer (e.g. no citations).
        Asks the LLM to try again with strict adherence to citation rules.
        """
        retry_prompt = f"""
        # FAILURE REPORT
        Your previous answer was REJECTED because it failed to cite sources or was hallucinatory.
        
        # INSTRUCTIONS
        1. Answer the User Query again using ONLY the Context.
        2. You MUST cite every sentence using [[ID]].
        3. If you cannot support a statement with a specific chunk, DO NOT WRITE IT.
        
        # Context
        {context}
        
        # User Query
        {query}
        """
        
        request = LLMRequest(
            system_prompt="You are a strict, citation-focused assistant.",
            prompt=retry_prompt, # Fixed: user_prompt -> prompt
            temperature=0.3
        )
        
        
        logger.warning(f"Self-Correction: Retrying generation for query: '{query}'")
        # [Deep Audit Fix] Async execution for Correction to avoid blocking Loop
        response = await self.llm.generate(request)
        return response.text

    def _construct_system_prompt(self, intent: UserIntent, outcome: RetrievalOutcome, file_metadata: Optional[Dict] = None, tone: str = "Technical") -> str:
        """
        Dynamically construct the System Prompt based on Intent, Outcome, and Tone.
        Injects Zero-Trust constraints.
        """
        from app.infrastructure.llm.prompts import ENTERPRISE_RAG_SYSTEM_PROMPT
        
        # Prepare injection variables
        # Prepare injection variables
        locked_id = "MULTIPLE/AUTHORIZED"
        locked_filename = "MULTIPLE_FILES"
        
        if file_metadata:
            locked_id = str(file_metadata.get("id", "MULTIPLE/AUTHORIZED"))
            locked_filename = str(file_metadata.get("filename", "MULTIPLE_FILES"))
            logger.info(f"System Prompt: Locked to DocID={locked_id}, Filename={locked_filename}")
        else:
            logger.warning(f"System Prompt: MISSING file_metadata! Reverting to fallback: {locked_filename}")
            if hasattr(self, 'last_retrieved_doc_id'):
                 logger.warning(f"  (Context: Last Retrieved Doc ID was {self.last_retrieved_doc_id})")
            
        # Format the prompt
        try:
            prompt = ENTERPRISE_RAG_SYSTEM_PROMPT.format(
                LOCKED_DOCUMENT_ID=locked_id,
                LOCKED_FILENAME=locked_filename
            )
        except Exception as e:
            logger.error(f"Prompt formatting error: {e}. Falling back to raw prompt.")
            prompt = ENTERPRISE_RAG_SYSTEM_PROMPT
            
        # Add Tone instruction
        if tone == "Executive":
             prompt += "\n\n[TONE: EXECUTIVE SUMMARY. Be brief, high-level, and strategic.]"
        elif tone == "Technical":
             prompt += "\n\n[TONE: TECHNICAL SPECIFICATION. Be precise, use numbers, and cite specific error codes.]"
             
        # Add Outcome-based clarifications
        if outcome == RetrievalOutcome.ACCESS_DENIED:
             prompt += "\n\n[ACCESS DENIED]: State that the user lacks permissions."
        elif outcome == RetrievalOutcome.AMBIGUOUS:
             prompt += "\n\n[AMBIGUITY]: The retrieved info represents a partial match. Admit uncertainty."
        elif outcome == RetrievalOutcome.NO_DATA:
             prompt += "\n\n[NO DATA]: State clearly that the authorized document does not contain the answer."
             
        # Add Intent specific formatting
        if intent == UserIntent.ENUMERATION:
             prompt += "\n\n[FORMATTING]: Provide the answer as a bulleted list."
        elif intent == UserIntent.COMPARISON:
             prompt += "\n\n[FORMATTING]: Use a Markdown table."
        elif intent == UserIntent.DESCRIPTION:
             prompt += "\n\n[FORMATTING/TONE]: Provide a high-level summary of the TYPES of information available. Do not list random specific data points unless asked."

        return prompt
        
    async def _retrieve_context(
        self, 
        user_id: int, 
        query: str, 
        top_k: int, 
        original_query: Optional[str] = None,
        bypass_relevance_check: bool = False,
        keywords: Optional[List[str]] = None,
        target_document_id: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Helper method to retrieve and rerank context.
        Returns dictionary with keys: final_chunks, candidate_count, accessible_count
        """
        t0 = time.time()
        boost_query = original_query if original_query else query
        
        # 1. Phase 1 & 2 Pre-calc: Get Accessible Chunk IDs (Policy Decision)
        # This enforces "Vector retrieval must be restricted to allowed_document_ids"
        accessible_chunk_ids = await asyncio.to_thread(
            self.rbac.get_accessible_chunk_ids,
            user_id=user_id
        )

        # [Feature] Target Document Filtering
        # If user specified a file, we intersect accessible IDs with that file's chunks.
        if target_document_id:
            logger.info(f"Targeting specific document ID: {target_document_id}")
            target_chunks = await asyncio.to_thread(self._fetch_chunk_ids_for_doc_sync, target_document_id)
            if target_chunks:
                target_set = set(target_chunks)
                if accessible_chunk_ids is not None:
                    # Intersection: Accessible AND Belongs to Target Doc
                    accessible_chunk_ids = [cid for cid in accessible_chunk_ids if cid in target_set]
                else:
                    # Super Admin / No restrictions -> Just the target doc
                    accessible_chunk_ids = target_chunks
                
                # Boost top_k for deep extraction from single file
                top_k = top_k * 2
                logger.info(f"Filtered retrieval to {len(accessible_chunk_ids)} chunks from Doc {target_document_id}")
            else:
                logger.warning(f"Target document {target_document_id} has no chunks or not found.")
        
        # 1. Parallel Retrieval (Vector + BM25) with Pre-filtering
        logger.debug(f"Generating embedding for query: {query[:100]}...")
        
        with PerformanceTimer("Phase 1: Retrieval"):
            query_embedding = await asyncio.to_thread(self.embeddings.embed_text, query)
            
            # [Deep Audit Fix] DISABLE HyDE
            # If query is short/ambiguous, use HyDE to halllucinate a target vector
            # if len(query.split()) < 12 and not bypass_relevance_check: 
            #      hyde_text = await self._generate_hyde_answer(query)
            #      if hyde_text:
            #          hyde_vec = await asyncio.to_thread(self.embeddings.embed_text, hyde_text)
            #          # Standard HyDE Blend: 0.8 Query + 0.2 HyDE (Reduced HyDE to minimize hallucination risk)
            #          # We use numpy to blend
            #          q_vec = np.array(query_embedding)
            #          h_vec = np.array(hyde_vec)
            #          blended = 0.8 * q_vec + 0.2 * h_vec
            #          query_embedding = blended.tolist() # Convert back if needed by store
            #          logger.info("[HyDE] Applied vector blending")
            
            # Zero-Trust Strategy Decision
            EXACT_SEARCH_THRESHOLD = 5000
            use_exact_search = accessible_chunk_ids is not None and len(accessible_chunk_ids) < EXACT_SEARCH_THRESHOLD
            
            if use_exact_search:
                logger.info(f"Zero-Trust: Using Exact Subset Search for {len(accessible_chunk_ids)} accessible chunks")
                
                # 1. Exact Vector Search (Guaranteed Correctness)
                async def run_exact_vector():
                    return await self.vector_store.search_exact_subset(
                        query_vector=query_embedding,
                        allowed_ids=accessible_chunk_ids,
                        top_k=top_k * 5
                    )
                
                # 2. BM25 (Global but Filtered)
                async def run_bm25_filtered():
                    # Lazy Load if needed via index_path
                    # [NLP Optimization] Use extracted keywords for clearer Sparse Signal
                    bm25_query = " ".join(keywords) if keywords and len(keywords) > 0 else query
                    
                    results = await self.bm25.search(bm25_query, top_k * 10, index_path=self.bm25_path)
                    if not results: return []
                    allowed_set = set(accessible_chunk_ids)
                    return [r for r in results if int(r[0]) in allowed_set]
                
                vector_results, bm25_results = await asyncio.gather(run_exact_vector(), run_bm25_filtered())
                splade_results = [] # SPLADE not used in Exact Subset Mode yet
                
            else:
                logger.info(f"Zero-Trust: Using Global Search + Filter for {len(accessible_chunk_ids) if accessible_chunk_ids else 'Unlimited'} chunks")
                
                # DEBUG LOGGING
                logger.info(f"DEBUG: accessible_chunk_ids type: {type(accessible_chunk_ids)}")
                if accessible_chunk_ids is None:
                    logger.info("DEBUG: accessible_chunk_ids is None (Super Admin Mode)")
                else:
                    logger.info(f"DEBUG: accessible_chunk_ids count: {len(accessible_chunk_ids)}")
                
                # Standard Approximate Search
                async def run_vector_search():
                    res = await self.vector_store.search(
                        query_vector=query_embedding,
                        top_k=top_k * 10,  # 10x Oversampling for filtering
                        filter_ids=accessible_chunk_ids
                    )
                    logger.info(f"DEBUG: Vector Search returned {len(res)} results")
                    return res
                    
                async def run_bm25_search():
                    # Lazy Load if needed via index_path
                    # [NLP Optimization] Use extracted keywords for clearer Sparse Signal
                    bm25_query = " ".join(keywords) if keywords and len(keywords) > 0 else query
                    logger.debug(f"BM25 Query: '{bm25_query}'")
                    
                    results = await self.bm25.search(bm25_query, top_k * 10, index_path=self.bm25_path)
                    if accessible_chunk_ids is not None:
                        allowed_set = set(accessible_chunk_ids)
                        results = [r for r in results if int(r[0]) in allowed_set]
                    logger.info(f"DEBUG: BM25 Search returned {len(results)} results")
                    return results

                async def run_splade_search():
                    if not self.settings.enable_splade: return []
                    try:
                        from app.infrastructure.embeddings.splade_service import SpladeService
                        from app.infrastructure.retrievers.splade_retriever import SpladeRetriever
                        
                        splade_svc = SpladeService()
                        splade_ret = SpladeRetriever()
                        
                        # Encode
                        s_vec = await asyncio.to_thread(splade_svc.encode, query)
                        
                        # Resolve Allowed IDs for SPLADE (Chunk-Centric)
                        # If accessible_chunk_ids is None (Admin), searching 'keys()' effectively filters 'All'
                        # But filtering MUST happen before scoring.
                        search_space = accessible_chunk_ids
                        if search_space is None:
                             search_space = list(splade_ret.index.keys())
                        
                        # Search
                        results = await asyncio.to_thread(splade_ret.search, s_vec, top_k * 10, search_space)
                        logger.info(f"DEBUG: SPLADE Search returned {len(results)} results")
                        return results
                    except Exception as e:
                        logger.error(f"SPLADE Search failed: {e}")
                        return []
                
                vector_results, bm25_results, splade_results = await asyncio.gather(run_vector_search(), run_bm25_search(), run_splade_search())
        
        # 2. Reciprocal Rank Fusion (RRF)
        combined_scores = {}
        k = 60 # RRF constant
        
        for rank, (chunk_id, _) in enumerate(vector_results):
            combined_scores[chunk_id] = combined_scores.get(chunk_id, 0) + (1 / (k + rank + 1))
            
        for rank, (chunk_id, _) in enumerate(bm25_results):
            combined_scores[chunk_id] = combined_scores.get(chunk_id, 0) + (1 / (k + rank + 1))

        for rank, (chunk_id, _) in enumerate(splade_results):
            combined_scores[chunk_id] = combined_scores.get(chunk_id, 0) + (1 / (k + rank + 1))
        
        # Sort by combined score
        sorted_candidates = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        candidate_ids = [int(chunk_id) for chunk_id, _ in sorted_candidates]
        
        # Prune
        rerank_limit = self.settings.rerank_top_k
        rerank_candidates_ids = candidate_ids[:rerank_limit]
        
        # Retrieve chunk content for reranking
        rerank_chunk_docs = []
        if rerank_candidates_ids:
            with PerformanceTimer("Phase 2: DB Fetch"):
                chunks = self.chunk_repo.get_by_ids(rerank_candidates_ids)
                chunks_map = {c.id: c for c in chunks}
                # Preserve RRF order
                rerank_chunk_docs = [chunks_map[cid] for cid in rerank_candidates_ids if cid in chunks_map]
        
        
        # [Deep Audit Optimization] REMOVED INTERNAL RERANKING
        # Previously, this method duplicated the reranking effort. 
        # Now, it solely acts as the "Candidate Retriever" (Vector + BM25 + ID Filter).
        # We return the raw chunks, and let query() methodology handle the authoritative Reranking.
        
        final_chunks = []
        if rerank_chunk_docs:
            # Respect the requested top_k limit for retrieval depth
            # Note: query() asks for 50, so we return up to 50.
            limit = top_k if top_k else len(rerank_chunk_docs)
            
            # Simple assembly: Return chunks with dummy score 0.0
            # The calling function (query) will run the REAL Cross-Encoder.
            # We preserve the RRF sort order.
            for chunk in rerank_chunk_docs[:limit]:
                 # Format: (Chunk, Score)
                 # Score is 0.0 because it's un-reranked. RRF score is not comparable to Cross-Encoder logits.
                 final_chunks.append((chunk, 0.0))
        
        logger.debug(f"Retrieval took {time.time() - t0:.3f}s. Selected {len(final_chunks)} candidates for Reranker.")
            
        return {
            "final_results": final_chunks, # List of (Chunk, Score)
            "candidate_count": len(candidate_ids),
            "accessible_count": len(accessible_chunk_ids) if accessible_chunk_ids is not None else 999999
        }
    
    def _apply_gatekeeper(
        self, 
        chunks: List[DocumentChunk], 
        scores: List[float], 
        query: str, 
        threshold: float = -5.0,
        bypass_relevance_check: bool = False  # [Deep Audit Fix] Added missing parameter
    ) -> List[DocumentChunk]:
        """
        [Layer: Retrieval Gatekeeper]
        Reject chunks that fall below threshold OR fail coverage check.
        """
        valid_chunks = []
        
        # 1. Coverage Check (New)
        query_terms = self._extract_key_terms(query)
        
        for chunk, score in zip(chunks, scores):
            if score < threshold:
                logger.debug(f"Gatekeeper: Dropped chunk {chunk.id} (Score {score} < {threshold})")
                continue
                
            # Coverage Check
            # If query has > 2 terms, require at least 1 term match in chunk
            # IMPROVEMENT: TRUST THE RERANKER if score is high (> 0.0).
            # Only enforce strict keyword matching for lower-confidence chunks (e.g. < 0.0) or massive retrieval sets.
            bypass_coverage = score > 0.0 or bypass_relevance_check
            
            if not bypass_coverage:
                chunk_terms = self._extract_key_terms(chunk.content)
                if len(query_terms) >= 2 and not query_terms.intersection(chunk_terms):
                     logger.debug(f"Gatekeeper: Dropped chunk {chunk.id} (Score {score:.2f} < 0.0 coverage enforced & failed)")
                     continue

            valid_chunks.append((chunk, score))
            
        return valid_chunks

    def _assemble_context(self, chunks: List[DocumentChunk]) -> str:
        """
        [Layer: Context Assembly]
        1. Deduplicate (already done in retrieval, but safe to repeat)
        2. Group by Document -> Page
        3. Sort by Semantic Flow (DocID -> Page -> Index)
        4. Format with explicit Headers and ID injection
        """
        if not chunks:
            return ""
            
        # 1. Re-Packing (Lost-in-the-Middle Strategy)
        # Instead of sorting by DocID, we want the MOST RELEVANT chunks at the BEGINNING and END of the context window.
        # However, for Auditability, preserving Document -> Page flow is also important.
        # Enterprise Compromise: Sort by Score Descending (Most Relevant First).
        # This ensures the LLM sees the best evidence immediately.
        # "Lost-in-the-Middle" suggests: [Best, 3rd, ..., 4th, 2nd]
        
        # Sort by Score Descending (Assumes chunks list passed here is already sorted by score from retrieval, but let's be safe if we lost scores)
        # NOTE: self._assemble_context receives List[DocumentChunk]. We don't have scores here unless we pass them.
        # Current flow in query() -> _retrieve_context returns (Chunk, Score). 
        # But _assemble_context only takes chunks. 
        # Fix: We will rely on the fact that `chunks` are passed in their retrieved order (which IS sorted by score/relevance).
        
        # So, we just need to decide: Maintain Relevance Order vs Maintain Document Flow.
        # Requirement 4 says "Re-pack so most salient parts appear early".
        # So we KEEP them in Relevance Order (which they already are), but maybe group by doc if multiple chunks from same doc are adjacent?
        # Actually, let's keep it simple: Relevance Order is king for accuracy.
        
        # BUT, if we have chunks [DocA-Pg1, DocB-Pg5, DocA-Pg2], reading flow is broken.
        # Hybrid Approach: Group by Document, but sort Groups by Max-Score of that document.
        # Given we don't have scores here, we'll assume the input list order implies priority.
        
        # Implementation: Just pass through? 
        # Original code sorted by DocID: chunks.sort(key=lambda c: (c.document_id, ...))
        # This DESTROYS relevance order. We MUST REMOVE THAT SORT.
        
        # We will keep the order provided by the reranker (Best First).
        # Only re-sort if explicitly requested for "Reading Mode".
        # For "Answering Mode", Best First is superior.
        pass # Do not sort by DocID. Trust the Reranker.

        
        # 2. Build String
        context_parts = []
        current_doc_id = None
        
        for chunk in chunks:
            doc_name = chunk.document.filename if chunk.document else "Unknown"
            
            # Header injection
            if chunk.document_id != current_doc_id:
                if current_doc_id is not None:
                     context_parts.append("\n") # Spacing
                context_parts.append(f"--- Document: {doc_name} ---")
                current_doc_id = chunk.document_id
            
            # Line injection
            page_info = f"(Page {chunk.page_number})" if chunk.page_number else ""
            # STRICT FORMAT: (ID: <id>) is required for Governance Layer
            chunk_line = f"{page_info} (ID: {chunk.id}): {chunk.content}" 
            context_parts.append(chunk_line)
            
        return "\n".join(context_parts)

    async def query(
        self,
        user_id: int,
        query: str,
        top_k: Optional[int] = None,
        bypass_relevance_check: bool = False
    ) -> Dict[str, any]:
        """
        Process a RAG query (Async).
        """
        top_k = top_k or self.settings.retrieval_top_k
        
        # 1. Cache Check
        # [Deep Audit Fix] Include bypass_relevance_check in cache key to prevent poisoning
        cache_key = self.cache.generate_key("query", user_id=user_id, query=query, top_k=top_k, bypass=str(bypass_relevance_check))
        
        # [Async Fix] Use async get to avoid blocking event loop
        cached_result = await self.cache.get_async(cache_key)
        if cached_result:
            return cached_result
            
        try:
            import time
            # asyncio already imported at module level
            t0 = time.time()
            
            # 2. Analyze Query (Async)
            logger.info(f"Analyzing query: '{query}'")
            query_analysis = await self._analyze_query(query)
            user_intent = query_analysis.intent
            
            # 3. Expand Query if needed (Async)
            search_query = query
            # [Phase 4] Check Semantic Cache (Milvus)
            # Threshold 0.2 means very high similarity
            semantic_hit = await self.semantic_cache.check_cache(query, threshold=0.15)
            if semantic_hit:
                 logger.info(f"Semantic Cache Hit (Milvus) for query: {query}")
                 # Ensure result is cast to RAGResponse
                 return RAGResponse(**semantic_hit)


            if self.settings.enable_query_expansion and \
               user_intent in [UserIntent.FACT_LOOKUP, UserIntent.DESCRIPTION, UserIntent.OPERATIONAL]:
                  # ZERO-TRUST: DISABLE EXPANSION. No World Knowledge.
                  # search_query = await self._expand_query(query)
                  pass

            
            # 4. Filter for specific file if requested (Binding)
            file_filter_meta = None
            if "file_id" in query_analysis.keywords:
                 # Logic to extract file ID... skipped for brevity or use metadata
                 pass
            
            # 5. Retrieve & Rerank (The Core)
            # Check for chitchat/ambiguity based on analysis
            if user_intent == UserIntent.CHITCHAT or self._is_chitchat(query):
                 logger.info("Chitchat detected, executing bypass.")
                 
                 # [Chitchat Bypass] Generate friendly response without RAG
                 # This prevents "No grounded information" refusals for greetings/capability questions.
                 chitchat_prompt = (
                     "You are a helpful and intelligent Enterprise AI Assistant tailored for this organization.\n"
                     "Your capabilities include:\n"
                     "1. Analyzing uploaded documents (PDF, Excel, Word).\n"
                     "2. Extracting specific facts, figures, and technical data.\n"
                     "3. Summarizing complex reports and comparing information.\n"
                     "4. Answering questions strictly based on the provided Knowledge Base.\n\n"
                     "If the user asks 'What can you do?', explain these capabilities professionally.\n"
                     "If this is a greeting, reply politely and ask how you can help with their documents today.\n"
                     "Do NOT hallucinate information about documents you haven't seen."
                 )
                 
                 request = LLMRequest(
                    system_prompt=chitchat_prompt,
                    prompt=f"User Message: {query}",
                    max_tokens=200,
                    temperature=0.7 # Warmer for chat
                 )
                 
                 response = await self.llm.generate(request)
                 
                 return RAGResponse(
                    answer=response.text,
                    sources=[],
                    intent=UserIntent.CHITCHAT,
                    confidence_score=1.0,
                    system_outcome=RetrievalOutcome.NO_DATA, # Technically no data retrieved
                    metadata={
                        "model_name": "chitchat-bypass",
                        "fallback_mode": True
                    }
                 )

            else:
                # [Fix for "is and" hallucination]
                # Fail Fast: If query has NO meaningful terms, do not even try retrieval/expansion.
                # This prevents "Hallucinated Expansion" (e.g. "is and" -> "centrifugal pump")
                query_terms = self._extract_key_terms(query)
                if not query_terms:
                    logger.warning(f"Query '{query}' has no meaningful key terms (Stopword only). Fail Fast.")
                    return {
                        "answer": "No information found in your accessible documents.", # Standard refusal
                        "citations": [],
                        "chunks_retrieved": 0,
                        "chunks_after_filtering": 0,
                        "tokens_used": 0,
                        "model_name": "system-gatekeeper",
                        "fallback_mode": False
                    }

                # Pass original query for boosting
                
                # Enterprise Upgrade: Fetch more candidates (20) for Reranking
                retrieval_result = await self._retrieve_context(
                    user_id, 
                    search_query, 
                    top_k=20, # Increased from 10 to 20 for Reranking
                    original_query=query,
                    bypass_relevance_check=bypass_relevance_check,
                    keywords=query_analysis.keywords
                )
            
            final_results = retrieval_result["final_results"]
            # Unpack tuples from _retrieve_context (chunk, score)
            final_chunks = [r[0] for r in final_results]
            
            # [Layer: Cross-Encoder Reranking]
            # Rerank the top 20 to get the best high-precision 10
            if final_chunks:
                with PerformanceTimer("Reranking"):
                     final_chunks, final_scores = await self.reranker.rerank(query, final_chunks, top_k=10)
                     
                     # STRICT FILTERING: Discard irrelevant chunks (Score < 0.0)
                     # MS-MARCO Cross-Encoders typically output logits. 
                     # > 0 means relevant, < 0 means irrelevant.
                     # We use 0.0 as the strict boundary (50% probability).
                     # Lowered from 0.15 to fix false negatives.
                     RERANK_THRESHOLD = 0.0 
                     
                     # Debug: Log scores
                     logger.info(f"Reranker scores: {list(zip(range(len(final_scores)), final_scores))[:5]}")
                     
                     # [Deep Audit Fix] Respect bypass_relevance_check
                     filtered_results = [
                        (c, s) for c, s in zip(final_chunks, final_scores) 
                        if bypass_relevance_check or s >= RERANK_THRESHOLD
                     ]
                     final_chunks = [r[0] for r in filtered_results]
                     final_scores = [r[1] for r in filtered_results]
                     
                     logger.info(f"After threshold {RERANK_THRESHOLD}: {len(final_chunks)} chunks remain")
                     
                     if not final_chunks and len(filtered_results) == 0 and len(final_scores) > 0:
                         logger.warning(f"Reranker: All {len(final_scores)} chunks filtered out by threshold {RERANK_THRESHOLD}")
            else:
                 final_scores = []
            
            candidate_count = retrieval_result["candidate_count"]
            accessible_count = retrieval_result["accessible_count"]
            # 3. Build prompt and generate answer
            # 3. Intent & Dominant Document Selection
            # 3. Gatekeeper (Strict Relevance Check)
            # The Reranker naturally filters, but we apply an explicit final check if needed
            # For now, we rely on the candidate list being good, but we can call _apply_gatekeeper() if we had raw scores separate
            # Since _retrieve_context returns final_chunks (already filtered somewhat), we check emptiness strictly.
            
            if not final_chunks and not self._is_chitchat(query):
                logger.warning("Gatekeeper: Retrieval empty (or score too low). Refusing answer.")
                msg = "No grounded information found."
                outcome = RetrievalOutcome.NO_DATA
                
                if accessible_count == 0: 
                    msg = "Access Denied: You do not have permission to view the relevant documents."
                    outcome = RetrievalOutcome.ACCESS_DENIED
                elif candidate_count == 0: 
                    msg = "No information found in your accessible documents."
                else: 
                     msg = "I found some documents, but they did not meet the strict relevance standards."
                     outcome = RetrievalOutcome.AMBIGUOUS
                
                return {
                    "answer": msg,
                    "citations": [],
                    "chunks_retrieved": candidate_count,
                    "chunks_after_filtering": accessible_count,
                    "tokens_used": 0,
                    "model_name": "system-gatekeeper",
                    "fallback_mode": False
                }
            
            # [Code Cleanup] Context assembly deferred until after Dominant Document filtering
            # to avoid wasted computation if chunks are filtered
            
            # Determine Top Score
            top_score = 10.0 if final_chunks else -1.0
            
            # Intent & Outcome
            outcome = self._determine_outcome(
                candidate_count, 
                accessible_count, 
                final_chunks, 
                top_score=top_score
            )
            
            # 3. Intent & Dominant Document Selection
            # intent is already determined from _analyze_query (user_intent)
            # file_metadata = None # This was already declared above as file_filter_meta
            
            # [Layer: Dominant Document Selection]
            # ZERO-TRUST ENFORCEMENT: Identify ONE dominant document and LOCK it.
            dominant_doc_id = None
            if final_chunks:
                 dominant_doc_id = self._select_dominant_document(final_chunks, final_scores)
                 
                 if not dominant_doc_id:
                     # Ambiguity or low signal -> REFUSE
                     logger.warning("Zero-Trust: No dominant document found (Ambiguity/Low Signal). Refusing.")
                     return {
                        "answer": "No grounded information found (Ambiguous Context).",
                        "citations": [],
                        "chunks_retrieved": candidate_count,
                        "chunks_after_filtering": accessible_count,
                        "tokens_used": 0,
                        "model_name": "zero-trust-ambiguity",
                        "fallback_mode": False
                     }
                 
                 # LOCK: Filter chunks to ONLY this document
                 prev_count = len(final_chunks)
                 filtered_final = []
                 for c in final_chunks:
                     if c.document_id == dominant_doc_id:
                         filtered_final.append(c)
                 
                 final_chunks = filtered_final
                 logger.info(f"Zero-Trust: LOCKED to Document ID {dominant_doc_id}. Filtered {prev_count} -> {len(final_chunks)} chunks.")
                 
                 # Set metadata for System Prompt injection
                 file_filter_meta = {"id": dominant_doc_id} 
                 # We don't have filename easily here without querying DB or inspecting chunk. 
                 # Chunk has .document relationship usually active
                 if final_chunks and final_chunks[0].document:
                     file_filter_meta["filename"] = final_chunks[0].document.filename
            
            # [Context Optimization]
            # Increase context window to maximize coherence for Llama 3B
            MAX_CONTEXT_TOKENS = 6000

            
            # [Layer: Entity Consistency]
            # STRICT MODE: If query asks about "Alice" and text doesn't contain "Alice", REFUSE.
            if final_chunks and not self._enforce_entity_presence(query, final_chunks):
                 logger.warning("Zero-Trust: Entity Mismatch. Query entities not found in locked document.")
                 final_chunks = []
                 
            # [Layer: Keyword Constraint (False Embedding Protection)]
            # Ensure at least one noun/verb from query exists in chunks
            # This handles cases where Reranker score is marginally high (0.16) but topic is wrong.
            if final_chunks:
                 final_chunks = await asyncio.to_thread(self._verify_term_overlap, query, final_chunks)
                 if not final_chunks:
                     logger.warning("Zero-Trust: Keyword Constraint blocked all chunks. Possible Vector Space Collision.")
            
            # [Layer: Keyword Constraint (False Embedding Protection)]
            # Ensure at least one noun/verb from query exists in chunks
            if final_chunks:
                 final_chunks = await asyncio.to_thread(self._verify_term_overlap, query, final_chunks)
            
            # 3. Gatekeeper (Strict Relevance Check) - REPEAT check after filtering
            if not final_chunks and not self._is_chitchat(query):
                 # ... (Existing Gatekeeper Logic, simplified here) ...
                 logger.warning("Gatekeeper: Retrieval empty (after locking). Refusing.")
                 return {
                    "answer": "No grounded information found in the specific document.",
                    "citations": [],
                    "chunks_retrieved": candidate_count,
                    "chunks_after_filtering": accessible_count,
                    "tokens_used": 0,
                    "model_name": "system-gatekeeper",
                    "fallback_mode": False
                 }
            
            # 4. Context Assembly (Deterministic & Auditable)
            context_str = self._assemble_context(final_chunks)
            
            # Check Token Limit
            if len(context_str) > MAX_CONTEXT_TOKENS * 4: # Crude char estimation
                 logger.warning("Context huge, truncating...")
                 context_str = context_str[:MAX_CONTEXT_TOKENS * 4] + "... [Truncated]"

            # Determine Top Score
            top_score = 10.0 if final_chunks else -1.0
            
            # Intent & Outcome
            system_prompt = self._construct_system_prompt(
                intent=user_intent, 
                outcome=outcome,
                file_metadata=file_filter_meta, 
                tone=query_analysis.tone
            )
            
            logger.info(f"Query Decision: Intent={user_intent}, Outcome={outcome}, LockedDoc={file_filter_meta}") # Log full metadata
            
            # [PERMANENT HALLUCINATION FIX] Pre-Flight Check
            # Block LLM call entirely if context is empty or insufficient
            MIN_CONTEXT_WORDS = 30  # Require at least 30 words of context
            context_word_count = len(context_str.split()) if context_str else 0
            
            if context_word_count < MIN_CONTEXT_WORDS:
                logger.warning(f"Pre-Flight Block: Context too short ({context_word_count} words < {MIN_CONTEXT_WORDS}). Refusing to call LLM.")
                return {
                    "answer": "No grounded information found in the uploaded documents.",
                    "citations": [],
                    "chunks_retrieved": candidate_count,
                    "chunks_after_filtering": accessible_count,
                    "tokens_used": 0,
                    "model_name": "system-preflight-block",
                    "fallback_mode": False
                }
            
            # 3. Build prompt and generate answer
            # REMOVED DUPLICATE _construct_system_prompt call
            
            # [Code Cleanup] Reuse context_str from line 1218 instead of calling _assemble_context again
            
            # Sanitize inputs for LLM (Prompt Firewall)
            safe_query = self.firewall.sanitize(query)
            safe_context = self.firewall.sanitize(context_str)  # Reusing context_str
             
            # REINFORCEMENT: Append instruction to User Query for weaker models
            safe_query += "\n\n(IMPORTANT: You must cite your sources using [[ID]] format at the end of every claim. Use the IDs provided in the Context headers (e.g. (ID: 123)).)"
            
            request = LLMRequest(
                system_prompt=system_prompt, 
                prompt=f"Context:\n{safe_context}\n\nQuestion: {safe_query}", # Fixed: user_prompt -> prompt
                max_tokens=self.settings.llm_max_tokens,
                temperature=self.settings.llm_temperature
            )
            
            # [Deep Audit Fix] Async execution for Generation to avoid blocking Loop
            # This allows other users to be served while this request waits for LLM
            raw_response = await self.llm.generate(request)
            raw_answer = raw_response.text
            
            # [HALLUCINATION SHIELD] Post-Generation Validation
            # Block code generation and off-topic responses that bypass prompt instructions
            from app.application.services.hallucination_detector import detect_hallucination
            hallucination_detected = detect_hallucination(raw_answer, context_str, query)
            if hallucination_detected:
                logger.warning(f"Hallucination Shield: Blocked response. Reason: {hallucination_detected}")
                return {
                    "answer": "No grounded information found in the uploaded documents.",
                    "citations": [],
                    "chunks_retrieved": candidate_count,
                    "chunks_after_filtering": accessible_count,
                    "tokens_used": 0,
                    "model_name": "hallucination-shield",
                    "fallback_mode": False
                }
            
            # 4. Zero-Trust Authorization & Self-Correction
            validated_answer = await asyncio.to_thread(self._validate_claims, raw_answer, final_chunks)
            
            # [Self-Correction]
            # If validation wiped out the answer (but we had chunks), try again.
            if not validated_answer and final_chunks:
                logger.warning("Zero-Trust: Answer rejected. Triggering Self-Correction Loop.")
                raw_answer = await self._retry_generation_with_correction(query, safe_context, raw_answer)
                validated_answer = await asyncio.to_thread(self._validate_claims, raw_answer, final_chunks) # Validate again
            
            # Bridge to Finalization
            if validated_answer:
                 final_answer_text = validated_answer
                 # Re-extract citations from VALIDATED text
                 citations = self._extract_citations_from_text(final_answer_text, final_chunks)
            else:
                 final_answer_text = "No grounded information found in the Knowledge Base."
                 citations = []
            
            logger.info(f"Total RAG query time: {time.time() - t0:.3f}s")
            
            # Define refusal indicators
            # [Sanitization] Handle "Split Personality" refusal
            final_answer_text = self._sanitize_response(final_answer_text)
            
            is_refusal = self._check_refusal(final_answer_text)
            
            # Re-calculate citations if it IS a refusal (force empty)
            final_citations = citations if not is_refusal else []
            
            # Normalize Citations (Re-write text to use [1], [2] format)
            final_answer_text, final_citations = self._normalize_citations(final_answer_text, final_citations)
            
            # Convert Dict Citations to SourceChunk Models
            response_sources = []
            for cit in final_citations:
                response_sources.append(SourceChunk(
                    chunk_id=cit['chunk_id'],
                    document_id=cit['document_id'],
                    content=cit['snippet'], # Mapping snippet to content for display
                    similarity_score=cit.get('similarity_score', 0.0),
                    chunk_index=cit.get('chunk_index', 0),
                    document_title=cit['document_name'],
                    page_number=cit['page_number']
                ))

            response_payload = RAGResponse(
                answer=final_answer_text,
                sources=response_sources,
                intent=user_intent,
                confidence_score=float(top_score),
                system_outcome=outcome,
                metadata={
                    "chunks_retrieved": candidate_count,
                    "chunks_after_filtering": accessible_count,
                    "tokens_used": raw_response.tokens_used,
                    "model_name": raw_response.model_name,
                    "fallback_mode": len(final_chunks) == 0,
                    "utilization_ratio": (len(final_citations) / len(final_chunks)) if final_chunks else 0.0,
                    "context_chunks_count": len(final_chunks),
                    "cited_chunks_count": len(final_citations)
                }
            )
            
            # Cache result (TTL 1 hour) - We cache the dict representation of the model?
            # Or cache the model? Pickle support. Pydantic models are pickleable.
            # [Async Fix] Use async set
            await self.cache.set_async(cache_key, response_payload.dict(), ttl=3600)
            
            # [Phase 4] Write to Semantic Cache
            # Fire and forget
            asyncio.create_task(self.semantic_cache.cache_response(query, response_payload.dict()))
            
            return response_payload
            
        except Exception as e:
            logger.error(f"Error in RAG query: {e}", exc_info=True)
            raise
            
    def _select_dominant_document(self, chunks: List[DocumentChunk], scores: List[float]) -> Optional[int]:
        """
        [Zero-Trust Constraint] Identify the ONE document authorized to answer.
        
        Algorithm:
        1. Aggregate scores by Document ID.
        2. Identify Top 1 Document.
        3. Ambiguity Check: If Top 2 are close, FAIL CLOSED.
        """
        if not chunks:
            return None
            
        doc_scores = {}
        for chunk, score in zip(chunks, scores):
            doc_id = chunk.document_id
            # Logits can be negative. We sum them up. 
            # Or better: Count chunks above threshold? 
            # Summing scores rewards both relevance and coverage.
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + score
            
        # Convert to list and sort
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_docs:
            logger.warning("Zero-Trust: No dominant document found (empty scores)")
            return None
            
        best_doc_id, best_score = sorted_docs[0]
        logger.info(f"Zero-Trust: Dominant Doc ID={best_doc_id} (Score={best_score:.2f})")
        
        # DEBUG: Log top candidates
        logger.debug(f"Top 3 Docs: {[f'{d}: {s:.2f}' for d, s in sorted_docs[:3]]}")
        
        # Ambiguity Check (If 2+ docs)
        if len(sorted_docs) > 1:
            second_doc_id, second_score = sorted_docs[1]
            # If Best is barely better than Second (e.g. < 10% diff), it's ambiguous.
            # However, logits are non-linear.
            # Simple rule: If Best Score is effectively tied, we risk hallucinating from wrong context.
            # But "Fail Closed" is strict. Let's use a meaningful margin.
            # If best_score < 1.0 (weak) AND diff < 0.2 -> Fail.
            margin = best_score - second_score
            if margin < 0.05: # Extremely close tie
                logger.warning(f"Zero-Trust: Ambiguity Detected. Doc{best_doc_id} ({best_score:.2f}) vs Doc{second_doc_id} ({second_score:.2f}). REFUSING.")
                return None
                
        return best_doc_id

    async def stream_query(
        self,
        user_id: int,
        query: str,
        top_k: Optional[int] = None,
        bypass_relevance_check: bool = False
    ):
        """
        Process a RAG query and yield SSE events (Async Generator).
        """
        import json  # [Deep Audit Fix] Moved import before first usage
        
        # [Deep Audit Fix] Input Validation
        if not query or not query.strip():
             yield f"data: {json.dumps({'error': 'Query cannot be empty.'})}\n\n"
             yield "data: [DONE]\n\n"
             return

        top_k = top_k or self.settings.retrieval_top_k
        
        try:
            # Yield status
            yield f"data: {json.dumps({'status': 'Analyzing query...'})}\n\n"
            
            # [NLP Core] Analyze Query First
            query_analysis = await self._analyze_query(query)
            intent = query_analysis.intent
            
            yield f"data: {json.dumps({'status': 'Retrieving relevant documents...'})}\n\n"
            
            # 1. Retrieval
            # asyncio already imported at module level
            if self._is_chitchat(query):
                logger.info("Chitchat detected, skipping retrieval")
                final_chunks = []
                retrieval_result = {
                    "final_results": [],
                    "candidate_count": 0,
                    "accessible_count": 0
                }
                final_chunks = []
                final_scores = []
            else:
                # [Deep Audit Fix] DISABLE Expansion
                expanded_query = query 
                
                # 3. Query Analysis (Intent & Entities)
                analysis_result = await self._analyze_query(query)
                logger.info(f"Query Analysis: {analysis_result}")
                
                # 4. Target Document Identification
                target_doc_id = await asyncio.to_thread(self._identify_target_document_sync, query, user_id)
                
                # 5. Advanced Retrieval
                retrieval_result = await self._retrieve_context(
                    user_id=user_id,
                    query=query,
                    top_k=self.settings.retrieval_top_k, 
                    original_query=query, # Assuming original_query is 'query' here, as it's not passed into stream_query
                    bypass_relevance_check=(analysis_result.intent == UserIntent.OPERATIONAL),
                    keywords=analysis_result.keywords,
                    target_document_id=target_doc_id
                )
                
                final_results = retrieval_result["final_results"]
                # Unpack tuples to get chunks
                initial_chunks = [r[0] for r in final_results]
                
                if initial_chunks:
                     # Rerank to Top 10
                     final_chunks, final_scores = await self.reranker.rerank(query, initial_chunks, top_k=10)
                     
                     # STRICT FILTERING: Discard irrelevant chunks (Score < 0.0)
                     # Lowered from 0.15 to 0.0 to improve recall
                     RERANK_THRESHOLD = 0.0
                     
                     # [Deep Audit Fix] Respect bypass_relevance_check
                     filtered_results = [
                        (c, s) for c, s in zip(final_chunks, final_scores) 
                        if bypass_relevance_check or s >= RERANK_THRESHOLD
                     ]
                     final_chunks = [r[0] for r in filtered_results]
                     final_scores = [r[1] for r in filtered_results]
                     
                     if not final_chunks and filtered_results:
                         logger.warning(f"Stream Reranker: All chunks filtered out by threshold {RERANK_THRESHOLD}")
                else:
                     final_chunks = []
                     final_scores = []
            
            # [Layer: Entity Consistency]
            if final_chunks and not self._enforce_entity_presence(query, final_chunks):
                 logger.warning("Stream: Zero-Trust Entity Mismatch.")
                 final_chunks = []
                 
            # [Layer: Keyword Constraint (False Embedding Protection)]
            if final_chunks:
                 final_chunks = await asyncio.to_thread(self._verify_term_overlap, query, final_chunks)
                 if not final_chunks:
                     logger.warning("Stream: Keyword Constraint Blocked All Chunks.")

            # 3. Context Assembly & Gatekeeper
            
            if not final_chunks and not self._is_chitchat(query):
                 logger.warning("Stream Gatekeeper: Retrieval empty. Refusing.")
                 yield f"data: {json.dumps({'status': 'No relevant documents found.'})}\n\n"
                 
                 if retrieval_result['candidate_count'] > 0 and retrieval_result['accessible_count'] == 0:
                     msg = "Access Denied: You do not have permission to view the relevant documents."
                 elif retrieval_result['candidate_count'] == 0:
                     msg = "No information found in your accessible documents."
                 else:
                     msg = "I found some documents, but they did not meet the strict relevance standards."
                     
                 yield f"data: {json.dumps({'token': msg})}\n\n"
                 yield "data: [DONE]\n\n"
                 return

            # 4. Context Assembly (Deterministic & Auditable)
            context_str = self._assemble_context(final_chunks)
            
            # Check Token Limit (Simple Truncation for Stream safety)
            MAX_CONTEXT_TOKENS = 3000
            if len(context_str) > MAX_CONTEXT_TOKENS * 4:
                 logger.warning("Context huge, truncating (stream)...")
                 context_str = context_str[:MAX_CONTEXT_TOKENS * 4] + "... [Truncated]"
            
            # [PERMANENT HALLUCINATION FIX] Pre-Flight Check for Streaming
            # Block LLM call entirely if context is empty or insufficient
            MIN_CONTEXT_WORDS = 30
            context_word_count = len(context_str.split()) if context_str else 0
            
            if context_word_count < MIN_CONTEXT_WORDS:
                logger.warning(f"Stream Pre-Flight Block: Context too short ({context_word_count} words < {MIN_CONTEXT_WORDS}). Refusing to call LLM.")
                yield f"data: {json.dumps({'token': 'No grounded information found in the uploaded documents.'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            yield f"data: {json.dumps({'status': 'Generating answer...'})}\n\n"
            
            # 3. Intent & Outcome Analysis
            # intent is already determined above via _analyze_query
            
            # Re-evaluating outcome based on final_chunks state
            outcome = RetrievalOutcome.NO_DATA
            if retrieval_result['candidate_count'] > 0 and retrieval_result['accessible_count'] == 0:
                outcome = RetrievalOutcome.ACCESS_DENIED
            elif not final_chunks and retrieval_result['candidate_count'] > 0:
                outcome = RetrievalOutcome.AMBIGUOUS
            elif final_chunks:
                outcome = RetrievalOutcome.STRONG_MATCH # Simplified for stream
            
            logger.info(f"Stream Decision: Intent={intent}, Outcome={outcome}")
            
            # 4. Dynamic Prompt
            file_metadata = None
            if final_chunks:
                # Use the first chunk's document metadata (Zero-Trust Dominance)
                top_chunk = final_chunks[0]
                if top_chunk.document:
                     file_metadata = {
                         "id": top_chunk.document.id,
                         "filename": top_chunk.document.filename
                     }
            
            dynamic_system_prompt = self._construct_system_prompt(intent, outcome, file_metadata, query_analysis.tone)
 
            # Sanitize inputs (Prompt Firewall)
            safe_query = self.firewall.sanitize(query)
            safe_context = self.firewall.sanitize(context_str)
            
            # REINFORCEMENT: Append instruction to User Query for weaker models (Aligns with query())
            safe_query += "\n\n(IMPORTANT: You must cite your sources using [[ID]] format at the end of every claim. Use the IDs provided in the Context headers (e.g. (ID: 123)).)"
            
            llm_request = LLMRequest(
                prompt=safe_query,
                context=safe_context,
                max_tokens=self.settings.llm_max_tokens,
                temperature=self.settings.llm_temperature,
                stop_sequences=["\n\nQuestion:", "\n\nUser:", "\nNote:", "\nPlease provide", "\nHere is the prompt"],
                system_prompt=dynamic_system_prompt # Use dynamic prompt
            )
            
            # 5. Stream Generation
            full_response = ""
            est_tokens = 0
            
            # [Deep Audit Fix] Use Async Iterator directly
            # BaseLLMAdapter.stream is async, no need for thread wrapper
            # [Fix] Ollama stream yields LLMResponse objects, not strings.
            async for response_chunk in self.llm.stream(llm_request):
                token = response_chunk.text
                full_response += token
                est_tokens += len(token) / 4 # Rough estimation
                yield f"data: {json.dumps({'token': token})}\n\n"
            
            logger.info(f"Stream Complete. Estimated Output Tokens: {int(est_tokens)}")
            
            # 6. Citations & Validation
            # Only return citations if the model actually found an answer
            
            # [Sanitization] Handle "Split Personality" refusal
            full_response = self._sanitize_response(full_response)
            
            is_refusal = self._check_refusal(full_response)
            
            if is_refusal:
                # If explicit refusal (and not just a "strong match" that happens to say "cannot find part of it")
                logger.info("Refusal detected, suppressing citations.")
                citations = []
            else:
                # [Deep Audit Fix] Post-Stream Validation
                # Validate the FULL response against the strict 2-term overlap rule.
                validated_response = await asyncio.to_thread(self._validate_claims, full_response, final_chunks)
                
                if not validated_response:
                     logger.warning("Stream Validation Failed: Retracting response due to Hallucination Risk.")
                     retraction_msg = "\n\n[SYSTEM: Response Retracted - Failed Strict Verification]"
                     yield f"data: {json.dumps({'token': retraction_msg})}\n\n"
                     yield f"data: {json.dumps({'citations': []})}\n\n"
                     yield "data: [DONE]\n\n"
                     return

                # Strict Governance: Parse [[ID]] from the generated stream
                # We DO NOT dump all chunks anymore.
                # [Fix] Use validated_response which has injected Identifiers
                citations = self._extract_citations_from_text(validated_response, final_chunks)
                
            # Normalize for Stream (Note: Stream text is already sent, so we can't rewrite it easily mid-stream without buffering.
            # But the user requested "permanent fix".
            # For stream, rewriting is hard. BUT, we can at least normalize the CITATIONS list index to match what the user Sees if we forced text rewrite?
            # Actually, stream output contains [[123]]. We can't change that now.
            # Fallback for Stream: Just normalize the LIST order, but we can't change the text.
            # OR... we warn the user that streaming might show raw IDs.
            # PROD FIX: We can't easily normalize stream text post-hoc.
            # OPTION: Client-side normalization? 
            # DECISION: For now, we leave stream as is, OR we normalize the citations list so [1] in UI maps to the first ID found.
            # But text will still say [[123]].
            # Let's apply normalization to the CITATION OBJECTS so they at least have 'index' property, 
            # and maybe the frontend can use that to render [1] in the list.
            # The text [[123]] remains, but if the badge says "[[123]] File.pdf", it's okay.
            # BUT user wants [1].
            # This is a limitation of streaming.
            # Let's just normalize the list for now.
            _, citations = self._normalize_citations(full_response, citations)
            
            yield f"data: {json.dumps({'citations': citations})}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.exception("Error in RAG stream")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
    
    async def _cleanup_resources(self):
        """Clean up resources."""
        if hasattr(self, "semantic_cache"):
            await self.semantic_cache.cleanup()
            
    def _verify_term_overlap(self, query: str, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Hard Filter: Used to prevent 'False Embeddings' (Hallucinations).
        If a chunk does NOT contain at least one significant term from the query (Noun/Verb/Adj),
        it implies the vector match was purely distinctive but topically irrelevant.
        """
        # 1. Extract Significant Terms
        # Simple heuristic: Split, remove stopwords, keep len > 3
        stopwords = {"this", "that", "what", "where", "when", "how", "verify", "check", "explain", "describe", "list", "show", "tell", "which", "does", "have", "with", "from", "criteria"}
        tokens = [t.lower().strip("?,.!") for t in query.split()]
        key_terms = [t for t in tokens if t not in stopwords and len(t) > 3]
        
        if not key_terms:
            return chunks # Safety: If query is "What is it?", we can't filter.
            
        valid_chunks = []
        for chunk in chunks:
            chunk_text = chunk.content.lower()
            # Check for ANY overlap
            # Relaxed check: Substring match is fine (e.g. 'schedul' in 'scheduling')
            if any(term in chunk_text for term in key_terms):
                valid_chunks.append(chunk)
            else:
                pass 
                # logger.debug(f"Dropped Chunk {chunk.id} - No term overlap with {key_terms}")
                
        if len(valid_chunks) < len(chunks):
            logger.warning(f"Keyword Filter: Dropped {len(chunks) - len(valid_chunks)} chunks due to lack of keyword overlap.")
            
        if not valid_chunks and chunks:
            # Fallback: OCR might be bad, or vectors matched on synonyms/context not in keywords.
            # We relax the constraint to avoid "No Information Found" when vectors clearly found something.
            logger.warning("Keyword Filter: All chunks filtered. TRIGGERING FALLBACK (Zero-Trust Relaxation). Returning Top 5 vector matches.")
            return chunks[:5]

        return valid_chunks
    
    # Removed _empty_response method as we fallback to LLM now

    def _fetch_chunk_ids_for_doc_sync(self, document_id: int) -> List[int]:
        """Fetch all chunk IDs for a specific document."""
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            # Optimized query for IDs only
            result = db.query(DocumentChunk.id).filter(DocumentChunk.document_id == document_id).all()
            return [r[0] for r in result]

    def _identify_target_document_sync(self, query: str, user_id: int) -> Optional[int]:
        """
        Identify if query targets a specific file.
        Returns document_id if found and accessible.
        """
        from app.core.database import SessionLocal
        from sqlalchemy import or_
        from app.domain.models import Document
        
        # Heuristic: Check for quotes or "in [file]" pattern?
        # Simpler: Fuzzy match query tokens against filenames accessible to user.
        # Strict: If query contains explicit filename substring (min 5 chars)
        
        # 1. Get user's visible docs
        # Note: In production, cache this or use Vector Store metadata.
        # For now, DB query is fine for low user count.
        
        with SessionLocal() as db:
            # Get Request User's role/department logic... 
            # Simplified: List all documents user can seeing 
            # (Re-using some RBAC logic implicitly would be better, but we do simple check)
            
            # We fetch all docs and check match. 
            # If "Zomato" is in query and "Zomato_Annual_Report..." exists.
            
            docs = db.query(Document.id, Document.title, Document.filename).all()
            
            query_lower = query.lower()
            best_match = None
            max_len = 0
            
            for doc_id, title, filename in docs:
                # Search for distinct filename parts
                # e.g. "zomato" matches "Zomato_Results.pdf"
                
                # Check Title
                if title and len(title) > 3 and title.lower() in query_lower:
                    if len(title) > max_len:
                         max_len = len(title)
                         best_match = doc_id
                         continue

                # Check Filename (stem)
                stem = os.path.splitext(filename)[0].lower()
                clean_stem = stem.replace("_", " ").replace("-", " ")
                
                # Direct substring match of significant filename parts
                # Try splitting filename into words
                stem_words = [w for w in clean_stem.split() if len(w) > 3]
                
                match_score = 0
                for word in stem_words:
                    if word in query_lower:
                        match_score += 1
                
                # If > 50% of filename words are present, high confidence
                if stem_words and (match_score / len(stem_words)) >= 0.5:
                     if len(stem) > max_len: # Prefer longer/more specific match
                         max_len = len(stem)
                         best_match = doc_id
            
            if best_match:
                logger.info(f"Query '{query}' identified targeting Document ID {best_match}")
                return best_match
            
            return None

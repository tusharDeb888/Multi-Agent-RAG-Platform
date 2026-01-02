"""
RAG Service for Retrieval-Augmented Generation.
Follows Single Responsibility Principle - only handles RAG operations.
"""
from typing import List, Dict, Optional
import numpy as np
import os
import time
import asyncio
import re
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
from app.infrastructure.llm.prompts import ENTERPRISE_RAG_SYSTEM_PROMPT
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.base import BaseVectorStore

from app.domain.repositories.chunk_repository import ChunkRepository
from app.domain.models import DocumentChunk
from app.application.services.rbac_service import RBACService
from app.core.config import get_settings
from app.domain.rag_types import UserIntent, RetrievalOutcome


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
        self.vector_store = vector_store or self._create_vector_store()
        self.rbac = rbac_service or RBACService(db)
        self.chunk_repo = ChunkRepository(db)
        
        # Initialize Cache
        from app.infrastructure.cache.cache_service import CacheService
        self.cache = CacheService()
        
        # Initialize Reranker
        from app.infrastructure.rankers.cross_encoder import CrossEncoderRanker
        self.ranker = CrossEncoderRanker()
        
        # Initialize BM25 Retriever
        from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever
        self.bm25 = SparseBM25Retriever()
        bm25_path = f"{self.settings.faiss_index_path}.bm25.pkl"
        if os.path.exists(bm25_path):
             self.bm25.load(bm25_path)
        else:
             logger.warning("BM25 index not found. Hybrid retrieval will be degraded.")
             
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
        # Same implementation as before
        if self.settings.vector_index_type.value == "milvus":
            from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
            return MilvusVectorStore()
            
        elif self.settings.vector_index_type.value == "oracle_vector":
            from app.infrastructure.vector_store.oracle_store import OracleVectorStore
            return OracleVectorStore()
            
        else:
            raise NotImplementedError(f"Vector store type {self.settings.vector_index_type} not implemented")
    
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
                f"You are a query optimizer. Your goal is to improve retrieval for a RAG system.\n"
                f"User Query: \"{query}\"\n\n"
                f"Task:\n"
                f"1. **Extract Entities**: Identify Names (e.g., 'Charlie'), Codes (e.g., 'PRJ_99'), or Locations. KEEP THESE EXACT.\n"
                f"2. **Identify Intent**: What specific document type or info is needed (e.g., 'Budget', 'Safety Policy')?\n"
                f"3. **Expansion**: Combine the extracted entities with relevant synonyms and keywords.\n"
                f"4. **Format**: Output ONLY the optimized search keyword string. No explanations.\n\n"
                f"Examples:\n"
                f"- Input: \"tell me about Charlie\"\n"
                f"- Output: \"Charlie employee profile responsibility project role Marketing Content Creation\"\n"
                f"- Input: \"distillation safety\"\n"
                f"- Output: \"distillation column safety protocols hazard procedures emergency shutdown\"\n\n"
                f"Optimized Query:"
            )
            llm_request = LLMRequest(
                prompt=prompt,
                max_tokens=60,
                temperature=0.1,  # Lower temperature for precision
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

    async def _classify_intent(self, query: str) -> UserIntent:
        """Classify user intent using LLM or heuristics."""
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
            
        # 2. LLM Fallback (Simulated or Lightweight)
        # For now, default to FACT_LOOKUP or DESCRIPTION based on length
        if len(query.split()) > 10:
             return UserIntent.DESCRIPTION
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

    def _construct_system_prompt(self, intent: UserIntent, outcome: RetrievalOutcome) -> str:
        """Build dynamic system prompt based on Intent and Outcome."""
        base_prompt = ENTERPRISE_RAG_SYSTEM_PROMPT
        
        instruction = ""
        
        # Intent-based instructions
        if intent == UserIntent.ENUMERATION:
             instruction += "\n\n[FORMATTING]: Provide the answer as a comprehensive, bulleted list."
        elif intent == UserIntent.OPERATIONAL:
             instruction += "\n\n[FORMATTING]: Provide the answer as a numbered step-by-step guide."
        elif intent == UserIntent.COMPARISON:
             instruction += "\n\n[FORMATTING]: Use a Markdown table to compare the items side-by-side."
             
        # Outcome-based instructions
        if outcome == RetrievalOutcome.ACCESS_DENIED:
             instruction += "\n\n[RESPONSE LOGIC]: The user does not have access to the relevant documents. State clearly that access is restricted. DO NOT confirm nor deny specific details."
        elif outcome == RetrievalOutcome.AMBIGUOUS:
             instruction += "\n\n[RESPONSE LOGIC]: The retrieved information is partial or low confidence. Admit uncertainty. Use phrases like 'The documents mention X, but do not explicitly state Y'."
        elif outcome == RetrievalOutcome.NO_DATA:
             instruction += "\n\n[RESPONSE LOGIC]: No relevant information was found. State clearly that the system does not contain this information. Do not hallucinate."
             
        return base_prompt + instruction
        
    async def _retrieve_context(
        self, 
        user_id: int, 
        query: str, 
        top_k: int, 
        original_query: Optional[str] = None
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
        
        # 1. Parallel Retrieval (Vector + BM25) with Pre-filtering
        logger.debug(f"Generating embedding for query: {query[:100]}...")
        
        with PerformanceTimer("Phase 1: Retrieval"):
            query_embedding = await asyncio.to_thread(self.embeddings.embed_text, query)
            
            # Zero-Trust Strategy Decision
            EXACT_SEARCH_THRESHOLD = 5000
            use_exact_search = accessible_chunk_ids is not None and len(accessible_chunk_ids) < EXACT_SEARCH_THRESHOLD
            
            if use_exact_search:
                logger.info(f"Zero-Trust: Using Exact Subset Search for {len(accessible_chunk_ids)} accessible chunks")
                
                # 1. Exact Vector Search (Guaranteed Correctness)
                async def run_exact_vector():
                    return await asyncio.to_thread(
                        self.vector_store.search_exact_subset,
                        query_vector=query_embedding,
                        allowed_ids=accessible_chunk_ids,
                        top_k=top_k * 5
                    )
                
                # 2. BM25 (Global but Filtered)
                async def run_bm25_filtered():
                    if self.bm25.is_fitted:
                        results = await asyncio.to_thread(self.bm25.search, query, top_k * 10) # Fetch more to allow filtering
                        allowed_set = set(accessible_chunk_ids)
                        return [r for r in results if int(r[0]) in allowed_set]
                    return []
                
                vector_results, bm25_results = await asyncio.gather(run_exact_vector(), run_bm25_filtered())
                
            else:
                logger.info(f"Zero-Trust: Using Global Search + Filter for {len(accessible_chunk_ids) if accessible_chunk_ids else 'Unlimited'} chunks")
                
                # Standard Approximate Search
                async def run_vector_search():
                    return await asyncio.to_thread(
                        self.vector_store.search,
                        query_vector=query_embedding,
                        top_k=top_k * 10,  # 10x Oversampling for filtering
                        filter_ids=accessible_chunk_ids
                    )
                    
                async def run_bm25_search():
                    if self.bm25.is_fitted:
                        results = await asyncio.to_thread(self.bm25.search, query, top_k * 10)
                        if accessible_chunk_ids is not None:
                            allowed_set = set(accessible_chunk_ids)
                            results = [r for r in results if int(r[0]) in allowed_set]
                        return results
                    return []
                
                vector_results, bm25_results = await asyncio.gather(run_vector_search(), run_bm25_search())
        
        # 2. Reciprocal Rank Fusion (RRF)
        combined_scores = {}
        k = 60 # RRF constant
        
        for rank, (chunk_id, _) in enumerate(vector_results):
            combined_scores[chunk_id] = combined_scores.get(chunk_id, 0) + (1 / (k + rank + 1))
            
        for rank, (chunk_id, _) in enumerate(bm25_results):
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
        
        # 3. Reranking
        final_chunks = []
        if rerank_chunk_docs:
            chunk_texts = [c.content for c in rerank_chunk_docs]
            
            with PerformanceTimer(f"Phase 3: Reranking ({len(chunk_texts)} chunks)"):
                ranked_results = await asyncio.to_thread(
                    self.ranker.rank,
                    query,
                    chunk_texts,
                    top_k=len(rerank_chunk_docs) # Rank all
                )
            
            top_k_results = ranked_results[:len(rerank_chunk_docs)]
            
            # Dynamic Thresholding
            # Dynamic Thresholding
            if top_k_results:
                # Apply Exact Entity Match Boost using EXTRACTED ENTITIES
                # If the user said "Helen", we boost chunks with "Helen"
                # Only if "Helen" was identified as an Entity by the LLM (or fallback logic)
                boosted_results = []
                
                # Use entities passed from expansion, OR fallback to tokenization of original query
                boost_phrase = original_query.lower().strip() if original_query else ""
                
                if original_query:
                     # Tokenize boost query (remove stopwords roughly)
                    stopwords = {"tell", "me", "about", "who", "is", "in", "the", "what", "are", "a", "an", "how", "does", "system", "work"}
                    boost_tokens = [t.lower() for t in original_query.split() if t.lower() not in stopwords and len(t) > 2]
                else:
                    boost_tokens = []
                    
                logger.debug(f"Boost tokens: {boost_tokens}, Phrase: '{boost_phrase}'")
                
                for idx, score in top_k_results:
                    chunk = rerank_chunk_docs[idx]
                    chunk_content = chunk.content.lower()
                    
                    # 1. Exact Phrase Match (Highest Priority)
                    # If user asks "Security-Tint Envelopes", we want ONLY that.
                    if len(boost_phrase) > 5 and boost_phrase in chunk_content:
                         logger.info(f"Boosting chunk {chunk.id} due to EXACT PHRASE match query")
                         score += 50.0 # Super Boost
                    
                    # 2. Token Match (Partial Priority)
                    else:
                        for token in boost_tokens:
                            if token in chunk_content:
                                logger.debug(f"Boosting chunk {chunk.id} due to token match '{token}'")
                                score += 15.0 # Moderate Boost
                                break # Apply boost once per chunk
                            
                    boosted_results.append((idx, score))
                
                # Re-sort after boosting
                boosted_results.sort(key=lambda x: x[1], reverse=True)
                
                best_score = boosted_results[0][1]
                logger.info(f"Reranker top score (after boost): {best_score}")
                
                # Determine Strictness Mode
                # If we have a Super Boost (Score > 40), we enforce STRICT filtering
                # to drop partial matches (e.g. "Envelopes" in "Project Management")
                strict_mode_threshold = 30.0 if best_score > 40.0 else -100.0
                
                # Deduplication Set
                seen_content_hashes = set()
                
                for idx, score in boosted_results:
                    chunk = rerank_chunk_docs[idx]
                    logger.debug(f"Chunk {chunk.id} score: {score}")
                    
                    # Deduplication
                    if chunk.content_hash in seen_content_hashes:
                        logger.debug(f"Skipping duplicate chunk {chunk.id} (hash {chunk.content_hash})")
                        continue
                    
                    # Logic:
                    # 1. Absolute floor: > -12.0
                    # 2. Relative floor: within 8.0 of best
                    # 3. Strict Mode: If strict_mode is active, score must be > 30.0
                    
                    passes_absolute = score > -12.0
                    passes_relative = score > (best_score - 8.0)
                    passes_strict = score > strict_mode_threshold
                    
                    if passes_absolute and passes_relative and passes_strict:
                        final_chunks.append(chunk)
                        seen_content_hashes.add(chunk.content_hash)
                    else:
                        logger.debug(f"Filtered chunk {chunk.id} (Score: {score}. Strict: {strict_mode_threshold})")
        
        logger.debug(f"Retrieval took {time.time() - t0:.3f}s. Selected {len(final_chunks)} chunks.")
        
        # Enforce top_k limit strictly
        if top_k is not None:
            final_chunks = final_chunks[:top_k]
            
        return {
            "final_chunks": final_chunks,
            "candidate_count": len(candidate_ids),
            "accessible_count": len(accessible_chunk_ids) if accessible_chunk_ids is not None else 999999
        }
        
    def _apply_gatekeeper(
        self, 
        chunks: List[DocumentChunk], 
        scores: List[float], 
        threshold: float = -5.0 # CrossEncoder score threshold (tuned)
    ) -> List[DocumentChunk]:
        """
        [Layer: Retrieval Gatekeeper]
        Reject chunks that fall below the relevance threshold.
        If NO chunks pass, the system will eventually refuse to answer.
        """
        valid_chunks = []
        for chunk, score in zip(chunks, scores):
            if score >= threshold:
                valid_chunks.append(chunk)
            else:
                logger.debug(f"Gatekeeper: Dropped chunk {chunk.id} (Score {score} < {threshold})")
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
            
        # 1. Sort: Document -> Page -> Index (Deterministic Flow)
        chunks.sort(key=lambda c: (c.document_id, c.page_number or 0, c.chunk_index))
        
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
        top_k: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Process a RAG query (Async).
        """
        top_k = top_k or self.settings.retrieval_top_k
        
        # 1. Cache Check
        cache_key = self.cache.generate_key("query", user_id=user_id, query=query, top_k=top_k)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        try:
            # 2. Retrieval
            import time
            import asyncio
            t0 = time.time()
            
            # Check for chitchat
            if self._is_chitchat(query):
                logger.info("Chitchat detected, skipping retrieval")
                retrieval_result = {
                    "final_chunks": [],
                    "candidate_count": 0, 
                    "accessible_count": 0
                }
            else:
                # Expand query if needed
                expanded_query = await self._expand_query(query)
                # Pass original query for boosting
                retrieval_result = await self._retrieve_context(
                    user_id, 
                    expanded_query, 
                    top_k, 
                    original_query=query
                )
            
            final_chunks = retrieval_result["final_chunks"]
            candidate_count = retrieval_result["candidate_count"]
            accessible_count = retrieval_result["accessible_count"]
            
            # 3. Build prompt and generate answer
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
            
            # 4. Context Assembly (Deterministic & Auditable)
            context_str = self._assemble_context(final_chunks)
            
            # Check Token Limit (Post-Assembly check or Pre-calc - _assemble_context builds full string)
            # Optimization: If context_str is massive, we might need to truncate inside assembly.
            # For now, we trust top_k * chunk_size fits reasonably, or we truncate heavily.
            # Let's add a simple truncate for safety
            MAX_CONTEXT_TOKENS = 3000
            if len(context_str) > MAX_CONTEXT_TOKENS * 4: # Crude char estimation
                 logger.warning("Context huge, truncating...")
                 context_str = context_str[:MAX_CONTEXT_TOKENS * 4] + "... [Truncated]"

            # Determine Top Score
            top_score = 10.0 if final_chunks else -1.0
            
            # Intent & Outcome
            intent = await self._classify_intent(query)
            outcome = self._determine_outcome(
                candidate_count, 
                accessible_count, 
                final_chunks, 
                top_score=top_score
            )
            
            logger.info(f"Query Decision: Intent={intent}, Outcome={outcome}")
            
            # Dynamic Prompt
            dynamic_system_prompt = self._construct_system_prompt(intent, outcome)
            
            # Sanitize inputs for LLM (Prompt Firewall)
            safe_query = self.firewall.sanitize(query)
            safe_context = self.firewall.sanitize(context_str)
            
            # REINFORCEMENT: Append instruction to User Query for weaker models
            safe_query += "\n\n(IMPORTANT: You must cite your sources using [[Doc ID]] format at the end of every claim. Use the IDs provided in the Context headers.)"
            
            llm_request = LLMRequest(
                prompt=safe_query,
                context=safe_context,
                max_tokens=self.settings.llm_max_tokens,
                temperature=self.settings.llm_temperature,
                stop_sequences=["\n\nQuestion:", "\n\nUser:", "\nNote:", "\nPlease provide", "\nHere is the prompt"],
                system_prompt=dynamic_system_prompt
            )
            
            t_llm_start = time.time()
            logger.debug("Starting LLM generation...")
            
            with PerformanceTimer("Phase 4: LLM Generation"):
                llm_response = await asyncio.to_thread(self.llm.generate, llm_request)
                
            logger.debug(f"LLM generation took {time.time() - t_llm_start:.3f}s")
            
            # 5. Governance Layer (Citation Audit)
            # Strict logic:
            # 1. Parse [[ID]] tags from LLM output.
            # 2. Verify EACH tag exists in final_chunks.
            # 3. IF mismatched, flag/log.
            # 4. Construct final citations list ONLY from validated tags.
            
            # Extract
            cited_ids = set()
            try:
                matches = re.findall(r'\[\[(\d+)\]\]', llm_response.text)
                cited_ids = {int(m) for m in matches}
                logger.info(f"LLM explicitly cited chunk IDs: {cited_ids}")
            except Exception as e:
                logger.warning(f"Failed to parse citations: {e}")

            # Validate & Filter
            citations = []
            seen_pages = set() # (doc_id, page_num)
            
            # Map valid IDs for O(1) checking
            valid_chunk_map = {c.id: c for c in final_chunks}
            
            # Fallback Logic:
            # If NO citations were found, but we had chunks, the LLM failed instruction.
            # For Audit safety, we DO NOT auto-cite top 3 blindly anymore in STRICT mode.
            # We only fallback if standard setting allows it. For Enterprise Hardening, we disable "blind" fallback.
            # However, prompt injection "Note: No relevant info found in these 3 docs" should not have citations.
            
            for cid in cited_ids:
                if cid in valid_chunk_map:
                    chunk = valid_chunk_map[cid]
                    doc_id = chunk.document_id
                    page_key = (doc_id, chunk.page_number)
                    
                    if page_key not in seen_pages:
                        citations.append({
                            "document_id": doc_id,
                            "document_name": chunk.document.filename if chunk.document else "Unknown",
                            "chunk_id": chunk.id,
                            "page_number": chunk.page_number
                        })
                        seen_pages.add(page_key)
                else:
                    logger.warning(f"Governance: Hallucinated Citation ID {cid} detected and removed.")

            if not citations and final_chunks:
                logger.warning("Governance: LLM generated answer but cited 0 sources (likely format fail).")
                # Optional: Force "Unverified" flag if UI supports it.

            logger.info(f"Total RAG query time: {time.time() - t0:.3f}s")
            
            # Define refusal indicators
            refusal_markers = [
                "cannot find the answer",
                "does not contain the answer",
                "unable to find the answer",
            ]
            is_refusal = any(marker in llm_response.text.lower() for marker in refusal_markers)
            
            result = {
                "answer": llm_response.text,
                "citations": citations if not is_refusal else [],
                "chunks_retrieved": candidate_count,
                "chunks_after_filtering": accessible_count,
                "tokens_used": llm_response.tokens_used,
                "model_name": llm_response.model_name,
                "fallback_mode": len(final_chunks) == 0
            }
            
            # Cache result (TTL 1 hour)
            self.cache.set(cache_key, result, ttl=3600)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in RAG query: {e}", exc_info=True)
            raise

    async def stream_query(
        self,
        user_id: int,
        query: str,
        top_k: Optional[int] = None
    ):
        """
        Process a RAG query and yield SSE events (Async Generator).
        """
        top_k = top_k or self.settings.retrieval_top_k
        import json
        
        try:
            # Yield status
            yield f"data: {json.dumps({'status': 'Retrieveing relevant documents...'})}\n\n"
            
            # 1. Retrieval
            import asyncio
            if self._is_chitchat(query):
                logger.info("Chitchat detected, skipping retrieval")
                final_chunks = []
            else:
                # Expand query if needed
                expanded_query = await self._expand_query(query)
                retrieval_result = await self._retrieve_context(user_id, expanded_query, top_k)
                final_chunks = retrieval_result["final_chunks"]
            
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
            
            yield f"data: {json.dumps({'status': 'Generating answer...'})}\n\n"
            
            # 3. Intent & Outcome Analysis
            intent = await self._classify_intent(query)
            
            # Streaming Retrieval logic needs to expose scores/counts to determine outcome
            # Ideally _retrieve_context returns this, but currently it returns dict
            # We need to extract top score from somewhere. For now, we assume 'strong' if chunks exist.
            # Reranker scores aren't easily passed out of _retrieve_context in current dict structure without mod.
            # Let's assume 'PARTIAL' if chunks exist, 'NO_DATA' if empty.
            
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
            dynamic_system_prompt = self._construct_system_prompt(intent, outcome)
            
            # Sanitize inputs (Prompt Firewall)
            safe_query = self.firewall.sanitize(query)
            safe_context = self.firewall.sanitize(context_str)
            
            llm_request = LLMRequest(
                prompt=safe_query,
                context=safe_context,
                max_tokens=self.settings.llm_max_tokens,
                temperature=self.settings.llm_temperature,
                stop_sequences=["\n\nQuestion:", "\n\nUser:", "\nNote:", "\nPlease provide", "\nHere is the prompt"],
                system_prompt=dynamic_system_prompt # Use dynamic prompt
            )
            
            # 5. Stream Generation
            stream_generator = self.llm.stream(llm_request)
            full_response = ""
            
            for token in stream_generator:
                full_response += token
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0)
            
            # 6. Citations
            # Only return citations if the model actually found an answer
            refusal_markers = [
                "cannot find the answer",
                "does not contain the answer",
                "unable to find the answer",
                "access is restricted",
                "system does not contain"
            ]
            is_refusal = any(marker in full_response.lower() for marker in refusal_markers)
            
            if is_refusal:
                # If explicit refusal (and not just a "strong match" that happens to say "cannot find part of it")
                logger.info("Refusal detected, suppressing citations.")
                citations = []
            else:
                citations = []
                seen_pages = set() # (doc_id, page_num)
                for chunk in final_chunks:
                    doc_id = chunk.document_id
                    doc_name = chunk.document.filename if chunk.document else "Unknown"
                    page_key = (doc_id, chunk.page_number)
                    
                    if page_key not in seen_pages:
                        citations.append({
                            "document_id": doc_id,
                            "document_name": doc_name,
                            "chunk_id": chunk.id,
                            "page_number": chunk.page_number
                        })
                        seen_pages.add(page_key)
            
            yield f"data: {json.dumps({'citations': citations})}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.exception("Error in RAG stream")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
    
    # Removed _empty_response method as we fallback to LLM now


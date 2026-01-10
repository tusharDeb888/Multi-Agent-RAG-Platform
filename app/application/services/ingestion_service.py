"""
Document Ingestion Service.
Handles document processing, OCR, chunking, and embedding generation.
"""
import os
import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
import pdfplumber
import docx
from app.infrastructure.ocr import paddle_ocr_wrapper as pytesseract  # PaddleOCR drop-in replacement
from PIL import Image
import io
import logging
import csv

# Suppress pdfminer internal warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)
# Fix for macOS OpenMP conflict (FAISS vs Torch vs Scikit-learn)
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
# Fix for Tokenizers parallelism deadlock (HuggingFace)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from sqlalchemy.orm import Session
from loguru import logger

from app.core.config import get_settings
from app.domain.models import Document, DocumentChunk, DocumentStatus
from app.domain.repositories.document_repository import DocumentRepository
from app.domain.repositories.chunk_repository import ChunkRepository
from app.infrastructure.embeddings.embedding_service import EmbeddingService
from app.infrastructure.vector_store.base import BaseVectorStore
from app.infrastructure.retrievers.sparse_bm25 import SparseBM25Retriever


# [Security] Allowed file extensions for ingestion
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.csv', '.xls', '.xlsx', '.ppt', '.pptx', '.png', '.jpg', '.jpeg'}

class IngestionService:
    def _is_text_meaningful(self, text: str) -> bool:
        """
        Heuristic to check if text is valid natural language or garbage/CID codes.
        Strategies:
        1. Alphanumeric Ratio: Logic text should be > 70% alphanumeric/spaces.
        2. Common Word Check: English text usually contains 'the', 'and', 'is', 'of'.
        """
        if not text: return False
        
        # 1. Alphanumeric Ratio
        valid_chars = sum(1 for c in text if c.isalnum() or c.isspace())
        ratio = valid_chars / len(text)
        if ratio < 0.6: # Relaxed threshold (PDFs can be messy)
             return False
             
        # 2. Common Word Check (if text is long enough)
        # Prevents "AGX:123 XYA:222" style garbage which might pass alnum ratio
        if len(text) > 100:
            common_words = {'the', 'and', 'is', 'of', 'in', 'to', 'for', 'with', 'on', 'at', 'report', 'date', 'page', 'total'}
            # Check normalized
            words = set(text.lower().split())
            intersection = words.intersection(common_words)
            if len(intersection) < 2:
                # If 100 chars and NO common words, suspicious.
                return False
                
        return True

    
    # Class-level lock for BM25 rebuilds (Debouncing)
    _bm25_lock = None # Initialize in methods or check
    _bm25_needs_rebuild = False

    async def _schedule_bm25_rebuild(self):
        """
        Schedule a BM25 rebuild in the background.
        Implements debouncing: If a rebuild is running, mark as dirty. 
        The runner will check dirty flag before exiting.
        """
        import asyncio
        
        # Initialize lock if needed (singleton pattern on class)
        if IngestionService._bm25_lock is None:
            IngestionService._bm25_lock = asyncio.Lock()
            
        if IngestionService._bm25_lock.locked():
            logger.info("BM25 Rebuild already running. Marking for subsequent run.")
            IngestionService._bm25_needs_rebuild = True
            return

        # Launch background task
        # We use create_task to detach from the current request context
        asyncio.create_task(self._run_bm25_rebuild_loop())

    async def _run_bm25_rebuild_loop(self):
        """
        Actual runner that respects the lock and dirty flag.
        """
        import asyncio
        if IngestionService._bm25_lock is None:
             IngestionService._bm25_lock = asyncio.Lock()

        # Try to acquire lock. If failed (race condition), just return (someone else got it)
        if IngestionService._bm25_lock.locked():
             IngestionService._bm25_needs_rebuild = True
             return
             
        async with IngestionService._bm25_lock:
            while True:
                IngestionService._bm25_needs_rebuild = False
                logger.info("Starting Background BM25 Index Rebuild...")
                try:
                    await self._rebuild_bm25_index_impl()
                except Exception as e:
                    logger.error(f"Background BM25 Rebuild Failed: {e}")
                
                # Check if new requests came in while we were working
                if not IngestionService._bm25_needs_rebuild:
                    break
                logger.info("New documents added during rebuild. Rerunning...")

    async def _rebuild_bm25_index_impl(self):
        """
        Rebuild BM25 index from scratch using all chunks in DB.
        """
        import asyncio
        from app.core.database import SessionLocal
        
        # logger.info("Triggering BM25 Index Rebuild...") 
        # (Logged by wrapper)
        try:
            # Fetch all chunks (Heavy operation!)
            # Optimization: Use iterator if possible, but BM25 fit needs memory.
            # For now, we load all.
            chunks = await asyncio.to_thread(self._fetch_all_chunks_sync)
            
            if not chunks:
                 logger.warning("No chunks found for BM25 rebuild.")
                 return
            
            # Optimization: If chunk count hasn't changed signifcantly?
            # Hard to know without keeping state.
            
            texts = [c.content for c in chunks]
            ids = [c.id for c in chunks]
            
            bm25 = SparseBM25Retriever()
            await bm25.fit(texts, ids)
            await bm25.save(self.settings.bm25_index_path)
            logger.info(f"BM25 Index Rebuilt with {len(ids)} chunks.")
            
        except Exception as e:
            logger.error(f"Failed to rebuild BM25 index: {e}")
            raise e

    def _fetch_all_chunks_sync(self):
        """Fetch all chunks from DB."""

        from app.core.database import SessionLocal
        with SessionLocal() as db:
             repo = ChunkRepository(db)
             # We need a custom query to get ALL chunks
             # repo.get_multi() might have a limit
             return db.query(DocumentChunk).all()
    """
    Service for ingesting and processing documents.
    """
    
    def __init__(
        self,
        db: Session,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[BaseVectorStore] = None
    ):
        self.db = db
        self.settings = get_settings()
        self.doc_repo = DocumentRepository(db)
        self.chunk_repo = ChunkRepository(db)
        self.embeddings = embedding_service or EmbeddingService()
        self.vector_store = vector_store or self._create_vector_store()
        
    def _create_vector_store(self) -> BaseVectorStore:
        """Create vector store instance."""
        if self.settings.vector_index_type == "oracle_vector":
            # TODO: Implement Oracle Vector Store
             from app.infrastructure.vector_store.oracle_store import OracleVectorStore
             return OracleVectorStore()
        else:
            # Default to Milvus
            from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
            return MilvusVectorStore()

    def _validate_file_path(self, file_path: str) -> bool:
        """
        [Security] Validate file path to prevent path traversal attacks.
        Returns True if path is valid, raises ValueError otherwise.
        """
        # 1. Check extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File type '{ext}' not allowed. Allowed: {ALLOWED_EXTENSIONS}")
        
        # 2. Check for path traversal
        # Resolve to absolute path and ensure it's within upload directory
        abs_path = os.path.abspath(file_path)
        upload_dir = os.path.abspath(self.settings.upload_dir)
        
        if not abs_path.startswith(upload_dir):
            logger.warning(f"[Security] Path traversal attempt detected: {file_path}")
            raise ValueError("Invalid file path: Access denied")
        
        return True

        return True

    # --- Sync DB Helpers (Non-Blocking) ---
    def _init_processing_sync(self, document_id: int) -> Optional[tuple]:
        """Initialize document processing status in DB."""
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            doc_repo = DocumentRepository(db)
            document = doc_repo.get_by_id(document_id)
            if not document: return None
            
            document.status = DocumentStatus.PROCESSING
            db.commit()
            return (document.file_path, document.filename)

    def _update_document_status_sync(self, document_id: int, status: DocumentStatus, error_message: str = None):
        """Update document status in DB."""
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            document = DocumentRepository(db).get_by_id(document_id)
            if document:
                document.status = status
                if error_message:
                    document.error_message = error_message
                if status == DocumentStatus.SEARCHABLE:
                    document.processed_at = datetime.utcnow()
                try:
                    db.commit()
                except Exception as e:
                     # Handle StaleDataError (row deleted) or other DB errors gracefully
                     logger.warning(f"Could not update status for doc {document_id} (likely deleted): {e}")
                     db.rollback()
    
    def _save_chunks_sync(self, document_id: int, chunk_objects: List[DocumentChunk]) -> List[int]:
        """Save chunk objects to DB and return IDs."""
        from app.core.database import SessionLocal
        # Note: chunk_objects passed here are transient (created outside session).
        # We need to merge/add them to the session.
        # But wait, DocumentChunk objects created in _process_batch already have data.
        # We can just use dicts or recreate them, OR just add them if they are clean.
        # Simplest: create new instances bound to this session or add_all.
        saved_ids = []
        try:
             with SessionLocal() as db:
                # 1. Pre-check: Does document still exist?
                # If ingestion takes long, user might have deleted it.
                from app.domain.models import Document
                doc_exists = db.query(Document).filter_by(id=document_id).count() > 0
                if not doc_exists:
                    logger.warning(f"Document {document_id} was deleted. Aborting chunk save.")
                    return []

                chunk_repo = ChunkRepository(db)
                # Re-binding objects to this session
                
                # Use data dicts to be safe against detached instance errors
                # BUT _process_batch creates them using constructor, so they are transient.
                # So add_all is fine.
                
                for chunk in chunk_objects:
                    # We need to make sure we don't carry over 'session' state
                    db.add(chunk)
                
                db.commit()
                for chunk in chunk_objects:
                    db.refresh(chunk)
                    saved_ids.append(chunk.id)
        except Exception as e:
            # Handle IntegrityError specifically or generic DB errors
            # ORA-02291 or others
            logger.error(f"Failed to save chunks for doc {document_id}: {e}")
            # If parent key missing, likely deleted.
            if "integrity" in str(e).lower() or "ora-02291" in str(e).lower():
                 logger.warning(f"Abort: Parent document {document_id} likely deleted during processing.")
            return []
            
        return saved_ids

    # --- Triage Layer ---
    def _triage_document(self, file_path: str) -> str:
        """
        [Fast Triage] Inspect first 3 pages to decide routing strategy.
        Returns: 'FAST' or 'OCR'
        """
        try:
            # FAST PATH for non-PDFs immediately
            ext = os.path.splitext(file_path)[1].lower()
            if ext != '.pdf':
                return 'FAST'

            # Composite Score Heuristic
            text_density_sum = 0
            image_area_ratio_sum = 0
            has_fonts = False
            pages_checked = 0

            with pdfplumber.open(file_path) as pdf:
                # Check up to first 3 pages
                for page in pdf.pages[:3]:
                    pages_checked += 1
                    
                    # 1. Text Density
                    text = page.extract_text() or ""
                    width, height = page.width, page.height
                    page_area = width * height if width and height else 1
                    text_density_sum += len(text) / page_area

                    # 2. Image Ratio
                    image_area = sum([img['width'] * img['height'] for img in page.images])
                    image_area_ratio_sum += image_area / page_area

                    # 3. Font Presence
                    if page.chars:
                        has_fonts = True

            if pages_checked == 0:
                return 'OCR' # Empty or weird PDF

            avg_text_density = text_density_sum / pages_checked
            avg_image_ratio = image_area_ratio_sum / pages_checked
            
            # Score Calculation (Normalized conceptual thresholds)
            # High Text Density (> 0.001 chars/pixel area approx? No, let's use absolute chars count/page approx)
            # Let's simplify: Avg Chars per page
            avg_chars = len(text) if pages_checked == 1 else (text_density_sum * page_area) # Rough approx
            
            # Revised Score Logic from Architect Plan
            # Score = (TextDensity * 0.5) + (FontPresence * 0.3) - (ImageRatio * 0.2)
            # We map "TextDensity" to normalized 0-1 (e.g. 500 chars = 1.0)
            norm_text = min(avg_chars / 500.0, 1.0)
            norm_font = 1.0 if has_fonts else 0.0
            norm_image = min(avg_image_ratio, 1.0)
            
            score = (norm_text * 0.5) + (norm_font * 0.3) - (norm_image * 0.2)
            
            # Threshold > 0.4 implies decent text and fonts, low image
            logger.info(f"Triage Score: {score:.2f} (Text={norm_text:.2f}, Font={norm_font}, Img={norm_image:.2f})")
            
            return 'FAST' if score > 0.4 else 'OCR'

        except Exception as e:
            logger.warning(f"Triage failed, defaulting to OCR path: {e}")
            return 'OCR'

    async def process_document(self, document_id: int) -> bool:
        """
        [Async Pipeline v2.0] Tiered, Streaming Ingestion.
        """
        import asyncio
        from app.core.database import SessionLocal
        
        t_start = datetime.utcnow()
        
        try:
            # 1. Initialize & Status
            # 1. Initialize & Status (Async DB)
            doc_info = await asyncio.to_thread(self._init_processing_sync, document_id)
            if not doc_info:
                logger.error(f"Document {document_id} not found")
                return False
            
            file_path, filename = doc_info
            
            # 2. Triage
            strategy = await asyncio.get_running_loop().run_in_executor(None, self._triage_document, file_path)
            logger.info(f"Ingestion Strategy for {filename}: {strategy}")
            
            # 3. Streaming Processing
            await asyncio.to_thread(self._update_document_status_sync, document_id, DocumentStatus.EXTRACTING)
            
            chunk_buffer = []
            BATCH_SIZE = 32
            is_first_batch = True
            global_chunk_index = 0
            
            async for page_data in self._process_stream(document_id, file_path, strategy):
                # Chunking (CPU)
                # handle list of one page
                page_chunks = await asyncio.get_running_loop().run_in_executor(None, self._chunk_text, [page_data])
                
                if not page_chunks:
                    continue
                    
                chunk_buffer.extend(page_chunks)
                
                # Check Batch Size
                while len(chunk_buffer) >= BATCH_SIZE:
                    batch = chunk_buffer[:BATCH_SIZE]
                    chunk_buffer = chunk_buffer[BATCH_SIZE:]
                    
                    await self._process_batch(document_id, batch, is_first_batch, global_chunk_index)
                    global_chunk_index += len(batch)
                    is_first_batch = False
            
            # 4. Final Flush
            if chunk_buffer:
                 await self._process_batch(document_id, chunk_buffer, is_first_batch, global_chunk_index)
                 global_chunk_index += len(chunk_buffer)
            
            # 5. Completion
            # 5. Completion (Async DB)
            await asyncio.to_thread(self._update_document_status_sync, document_id, DocumentStatus.SEARCHABLE)
             
            # Save Vector Index
            # Save Vector Index
            if hasattr(self.vector_store, 'save'):
                 await self.vector_store.save(self.settings.index_storage_path)

            # Rebuild BM25 Index (Crucial for Hybrid Search) - Run in Background
            await self._schedule_bm25_rebuild()

            # [SPLADE Persistence] Save once flow is complete
            if self.settings.enable_splade:
                 try:
                     from app.infrastructure.retrievers.splade_retriever import SpladeRetriever
                     await asyncio.to_thread(SpladeRetriever().save)
                 except Exception as e:
                     logger.error(f"Failed to save SPLADE index: {e}")

            elapsed = (datetime.utcnow() - t_start).total_seconds()
            logger.info(f"Ingestion Complete (v2.0) for {filename}. Strategy={strategy}, Chunks={global_chunk_index}, Time={elapsed:.2f}s")
            return True

        except Exception as e:
            # [Fix] Unsafe logging fixed. Don't use f-string with exception if it contains braces.
            logger.error(f"Ingestion Failed for {document_id}")
            logger.exception(e) # This properly logs trace + message without formatting issues
            logger.exception(e) # This properly logs trace + message without formatting issues
            await asyncio.to_thread(self._update_document_status_sync, document_id, DocumentStatus.FAILED, str(e)[:4000])
            return False

    async def _process_batch(self, document_id: int, chunks_data: List[Dict], is_first_batch: bool, start_index: int):
        """Process a batch of chunks: Store DB -> Embed -> Index."""
        import asyncio
        from app.core.database import SessionLocal
        loop = asyncio.get_running_loop()
        
        chunk_objects = []
        texts = []
        
        for i, c in enumerate(chunks_data):
            real_index = start_index + i
            content = c["content"]
            # content hash
            c_hash = hashlib.sha256(content.encode()).hexdigest()
            texts.append(content)
            
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=real_index,
                content=content,
                content_hash=c_hash,
                page_number=c["page_number"],
                start_char=c["start_char"],
                end_char=c["end_char"]
            )
            chunk_objects.append(chunk)

        # DB Insert (Bulk)
        # DB Insert (Bulk & Async)
        chunk_ids = await asyncio.to_thread(self._save_chunks_sync, document_id, chunk_objects)
        
        if not chunk_ids:
            logger.warning(f"Batch processing aborted: No chunks saved for doc {document_id} (Deleted or DB Error).")
            return

        # Embed (GPU/Heavy CPU)
        
        # Embed (GPU/Heavy CPU)
        # Always update status to EMBEDDING to indicate progress
        await asyncio.to_thread(self._update_document_status_sync, document_id, DocumentStatus.EMBEDDING)
        
        t0 = datetime.utcnow()
        logger.info(f"Generating embeddings for batch of {len(texts)}...")
        # Generate embeddings (CPU-bound, offload to thread)
        embeddings = await asyncio.to_thread(self.embeddings.embed_batch, texts)
        dt_embed = (datetime.utcnow() - t0).total_seconds()
        logger.debug(f"Batch Embeddings generated in {dt_embed:.2f}s")
        
        # [SPLADE Integration] Generate Sparse Vectors
        if self.settings.enable_splade:
             try:
                 from app.infrastructure.embeddings.splade_service import SpladeService
                 from app.infrastructure.retrievers.splade_retriever import SpladeRetriever
                 
                 # Initialize (Singletons)
                 splade_svc = SpladeService()
                 splade_retriever = SpladeRetriever()
                 
                 t1 = datetime.utcnow()
                 logger.info(f"Generating SPLADE sparse vectors for batch of {len(texts)}...")
                 # Run encoding in thread to avoid blocking loop
                 sparse_vectors = await asyncio.to_thread(splade_svc.encode_batch, texts)
                 dt_splade = (datetime.utcnow() - t1).total_seconds()
                 logger.debug(f"Batch SPLADE generated in {dt_splade:.2f}s")
                 
                 # Update Index
                 for cid, svec in zip(chunk_ids, sparse_vectors):
                     splade_retriever.add(cid, svec)
                     
                 # DEFERRED: Save Index is now done at the end of process_document
                 # to prevent O(N^2) I/O bottleneck.
                 
             except Exception as e:
                 logger.error(f"SPLADE Indexing failed for batch: {e}")
                 # Fail-open? No, acceptable to continue dense-only if SPLADE fails?
                 # Prompt says "SPLADE failures must NOT crash ingestion".
                 # So we log and continue.

        
        # Index
        await asyncio.to_thread(self._update_document_status_sync, document_id, DocumentStatus.INDEXING)
        metadata = [{"document_id": document_id} for _ in chunk_ids]
        await self.vector_store.add_vectors(embeddings, chunk_ids, metadata)

        # Status Update using PARTIAL (Async)
        if is_first_batch:
             await asyncio.to_thread(self._update_document_status_sync, document_id, DocumentStatus.PARTIAL)
             logger.info(f"Doc {document_id} marked PARTIAL_SEARCHABLE")

    async def _process_stream(self, document_id: int, file_path: str, strategy: str):
        """
        Generate pages one by one based on strategy.
        Yields: dict(page_number, content)
        """
        import asyncio
        loop = asyncio.get_running_loop()
        ext = os.path.splitext(file_path)[1].lower()

        # Generator for FAST PATH (Text-heavy PDF or other files)
        if strategy == 'FAST' or ext != '.pdf':
            # Use streaming generator to prevent memory spikes and loop blocking
            # We must iterate the generator in a way that yields control
            # Since _extract_text_fast_wrapper was blocking-list, we need a new approach
            # We'll use a thread to run the extraction and push to a queue, or just offload chunks?
            # Simpler: The extractors are synchronous. Run them in a thread.
            
            # Problem: _extract_text returns a List. We want it to yield.
            # Fix: We'll modify _extract_text_fast_wrapper to be a generator, 
            # but since we can't easily change the synchronous extractors (pdfplumber usage) to async without rewrite,
            # we will keep the "load all" for non-PDFs (usually small) but OPTIMIZE PDF fast path.
            
            if ext == '.pdf':
                # Custom streaming for PDF Fast Path
                # It yields chunks directly (dictionaries), not coroutines
                async for page in self._extract_pdf_pages_stream(file_path):
                    if page:
                        yield page
            else:
                 # Legacy dispatch for other types (Docx, etc - usually smaller)
                 content_list = await loop.run_in_executor(None, self._extract_text_fast_wrapper, file_path, ext)
                 for page in content_list:
                     yield page
        
        # Generator for OCR PATH (Page-level selective)
        elif strategy == 'OCR' and ext == '.pdf':
             # Adaptive Concurrency
             # If using Local Vision/Ollama, we must be conservative to avoid GPU OOM or Queue Stalls.
             base_concurrency = self.settings.ingestion_workers or 4
             
             if self.settings.vision_provider in ["ollama", "local"]:
                 # Throttle for local OCR
                 CONCURRENCY_LIMIT = max(1, base_concurrency // 2)
                 logger.info(f"Local AI detected. Throttling ingestion concurrency to {CONCURRENCY_LIMIT}")
             else:
                 CONCURRENCY_LIMIT = base_concurrency
                 logger.info(f"Processing PDF with concurrency {CONCURRENCY_LIMIT}")
             
             with pdfplumber.open(file_path) as pdf:
                 total_pages = len(pdf.pages)
                 logger.info(f"Target: {total_pages} pages")
                 
                 # Process in chunks of pages to allow yielding results progressively
                 for i in range(0, total_pages, CONCURRENCY_LIMIT):
                     batch_pages = pdf.pages[i : i + CONCURRENCY_LIMIT]
                     batch_indices = range(i, i + len(batch_pages))
                     
                     tasks = []
                     
                    # 1. Preparation Phase (Offloaded to Executor to avoid blocking loop)
                    
                     def _prepare_ocr_batch_sync():
                         local_tasks = []
                         for idx, page in zip(batch_indices, batch_pages):
                              try:
                                  text = page.extract_text()
                                  
                                  if text and len(text.strip()) > 100:
                                      local_tasks.append({"type": "text", "page_num": idx+1, "content": text})
                                  else:
                                      # OCR Needed: Create Image immediately
                                      logger.info(f"Page {idx+1}: Text poor/missing. Queuing for OCR...")
                                      im = page.to_image(resolution=300).original
                                      local_tasks.append({"type": "ocr_job", "page_num": idx+1, "image": im})
                              except Exception as e:
                                  logger.error(f"Page {idx+1} Prep failed: {e}")
                                  local_tasks.append({"type": "error", "page_num": idx+1, "content": ""})
                         return local_tasks

                     tasks = await loop.run_in_executor(None, _prepare_ocr_batch_sync)

                     # 2. Execution Phase (Parallel for OCR)
                     # Identify OCR jobs
                     ocr_coroutines = []
                     ocr_indices = [] # Map back to tasks array
                     
                     for t_idx, task in enumerate(tasks):
                         if task["type"] == "ocr_job":
                             # Create future
                             # _run_ocr_on_image is CPU bound (Tesseract) or helper for Vision
                             # We run it in executor
                             future = loop.run_in_executor(None, self._run_ocr_on_image, task["image"])
                             
                             # Wrap with timeout
                             coro = asyncio.wait_for(future, timeout=120.0)
                             ocr_coroutines.append(coro)
                             ocr_indices.append(t_idx)

                     # Wait for OCR results
                     if ocr_coroutines:
                         try:
                             results = await asyncio.gather(*ocr_coroutines, return_exceptions=True)
                             
                             # Update tasks with results
                             for i, res in enumerate(results):
                                 original_idx = ocr_indices[i]
                                 if isinstance(res, Exception):
                                     logger.error(f"OCR failed for page {tasks[original_idx]['page_num']}: {res}")
                                     tasks[original_idx] = {"type": "error", "page_num": tasks[original_idx]['page_num'], "content": ""}
                                 else:
                                     tasks[original_idx] = {"type": "text", "page_num": tasks[original_idx]['page_num'], "content": res}
                         except Exception as e:
                             logger.error(f"Batch OCR failed: {e}")

                     # Yield Results in Order
                     for task in tasks:
                         if task["type"] == "text" and task.get("content"):
                             p_num = task.get("page_num", task.get("page_number"))
                             yield {"page_number": p_num, "content": task["content"]}
                             
    def _run_ocr_on_image(self, image_obj) -> str:
        """Use hybrid OCR module (Strict Text Only) with Vision Fallback."""
        from app.application.services.hybrid_ocr import perform_hybrid_ocr
        from app.application.services.vision_service import VisionService
        
        # Initialize Vision Service for fallback
        # Ideally this should be singleton or injected, but for now lazy-load is safe
        vision_svc = None
        use_vision = False
        try:
            if self.settings.vision_provider != "none":
                vision_svc = VisionService()
                use_vision = True
        except Exception as e:
            logger.warning(f"Could not init VisionService: {e}")

        # Zero-Trust Relaxed: Vision allowed for fallback
        return perform_hybrid_ocr(image_obj, vision_service=vision_svc, use_vision=use_vision)



    def _extract_text(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract text from PDF, using OCR if necessary.
        
        Returns:
            List of dicts with page_number and content
        """
        pages_content = []
        
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    
                    # 1.a Explicit Table Extraction (Enterprise Fix)
                    try:
                        tables = page.extract_tables()
                        if tables:
                            logger.info(f"Found {len(tables)} tables on page {i+1}")
                            table_mds = []
                            for table in tables:
                                # Remove empty rows/cols
                                cleaned_table = [[str(cell or "").replace("\n", " ").strip() for cell in row] for row in table if any(row)]
                                if not cleaned_table: continue
                                
                                # Convert to Markdown
                                # Ensure minimal columns
                                num_cols = max(len(row) for row in cleaned_table)
                                if num_cols < 2: continue # Skip trivial lists
                                
                                # Header
                                headers = cleaned_table[0]
                                # Pad row if needed
                                headers += [""] * (num_cols - len(headers))
                                header_str = "| " + " | ".join(headers) + " |"
                                separator = "| " + " | ".join(["---"] * num_cols) + " |"
                                
                                body_str = ""
                                for row in cleaned_table[1:]:
                                    # Pad row
                                    row += [""] * (num_cols - len(row))
                                    body_str += "| " + " | ".join(row) + " |\n"
                                
                                table_md = f"\n\n**Structured Table:**\n{header_str}\n{separator}\n{body_str}"
                                table_mds.append(table_md)
                            
                            if table_mds:
                                text += "\n".join(table_mds)
                    except Exception as e_table:
                        logger.warning(f"Table extraction failed for page {i+1}: {e_table}")

                    # Heuristic to detect "garbage" OCR or handwriting noise
                    def is_garbage(t):
                        if not t: return True
                        
                        # Filter out URLs for garbage detection (Cheat Sheets are mostly URLs)
                        clean_t = " ".join([w for w in t.split() if not w.startswith(('http', 'www', 'ftp'))])
                        
                        # RESCUE LOGIC: If text contains specific cheat-sheet keywords, accept it even if it looks messy
                        if any(k in t.lower() for k in ['happy number', 'leetcode', 'geeksforgeeks', 'pattern', 'list', 'tree', 'graph']):
                            return False

                        if not clean_t.strip(): return False # If mostly URLs, it's valid!
                        
                        # 0. Massive single-word garbage (e.g. Base64, Encrypted stream)
                        # Check on CLEAN text only
                        # Relaxed to 80 to allow for long technical tokens/URLs
                        if len(clean_t) > 80 and " " not in clean_t:
                            return True
                            
                        # 1. Repeating chars (e.g. VVV, LLL) - common in lined paper OCR
                        import re
                        if re.search(r'(.)\1{3,}', clean_t): 
                            return True
                            
                        # 2. Dictionary check (very basic)
                        words = clean_t.lower().split()
                        
                        # 3. Average word length check (detects concatenated garbage)
                        if words:
                            avg_len = sum(len(w) for w in words) / len(words)
                            if avg_len > 25: # Very suspicious (normal is ~5)
                                return True

                        if len(words) > 20:
                            common = {'the', 'and', 'a', 'of', 'to', 'in', 'is', 'it', 'for', 'on', 'with', 'as', 'at',
                                     'question', 'pattern', 'link', 'medium', 'hard', 'easy', 'code', 'data',
                                     'error', 'exception', 'traceback', 'log', 'server', 'client', 'http', 'https',
                                     'config', 'file', 'path', 'user', 'system', 'database', 'table', 'row', 'column'} # Added technical terms
                            hit_rate = sum(1 for w in words if w in common) / len(words)
                            if hit_rate < 0.05: # Relaxed from 0.1 to 0.05 for dense technical logs
                                return True
                        return False

                    # If text is empty, too short, OR GARBAGE, try OCR
                    if not text or len(text.strip()) < 100 or is_garbage(text):
                        if self.settings.enable_ocr:
                            logger.info(f"Performing OCR on page {i+1} (text length: {len(text.strip()) if text else 0})")
                            # Convert page to image
                            im = page.to_image(resolution=300)
                            try:
                                text = pytesseract.image_to_string(im.original, timeout=30)
                                # Sanity check OCR result
                                if is_garbage(text): 
                                    logger.warning(f"OCR returned garbage for page {i+1}. Discarding.")
                                    text = ""
                            except RuntimeError as e:
                                logger.warning(f"OCR timed out or failed for page {i+1}: {e}")
                                if is_garbage(text): text = "" 
                            finally:
                                # Explicitly release memory
                                # if 'im' in locals(): del im # Keep 'im' for Vision check below
                                import gc
                                gc.collect()
                        else:
                            logger.warning(f"Page {i+1} has little text and OCR is disabled")
                    
                    if (not text or len(text.strip()) < 100 or is_g_check):
                        # Zero-Trust: Vision AI is REMOVED.
                        # If OCR failed and text is garbage, we admit defeat or log warning.
                        logger.warning(f"Page {i+1}: Text quality poor after OCR. Marking potential data loss.")

                    
                    if text:
                        logger.info(f"FINAL TEXT for Page {i+1} (Len={len(text)}): {text[:200].replace(chr(10), ' ')}...")
                        pages_content.append({
                            "page_number": i + 1,
                            "content": text
                        })
                        
                    # Yield control slightly to check for cancellation/prevent CPU starvation
                    # [Code Cleanup] Removed blocking time.sleep(0.1) - causes thread blocking
                    pass
                        
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            raise
            
        return pages_content

    def _extract_from_docx(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from DOCX."""
        try:
            doc = docx.Document(file_path)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            
            content = "\n".join(full_text)
            # DOCX doesn't have "pages" strictly, treat as 1 page
            return [{"page_number": 1, "content": content}]
        except Exception as e:
            logger.error(f"Error reading DOCX {file_path}: {e}")
            raise

    def _extract_from_txt(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from TXT."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return [{"page_number": 1, "content": content}]
        except Exception as e:
            logger.error(f"Error reading TXT {file_path}: {e}")
            raise

    def _extract_from_image(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract text from Image using OCR + Vision AI.
        """
        try:
            image = Image.open(file_path)
            
            # 1. OCR (Text Extraction)
            text = pytesseract.image_to_string(image)
            
            # 2. Final check
            logger.info(f"OCR result for image {file_path}: {len(text)} chars")

            
            return [{'page_number': 1, 'content': text}]
        except Exception as e:
            logger.error(f'Error extracting from image {file_path}: {e}')
            raise
        # [Code Cleanup] Removed unreachable 'return pages_content' - variable was undefined

    def _extract_from_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from CSV."""
        try:
            content_lines = []
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.reader(f)
                for row in reader:
                    # Join valid cells with space
                    row_text = " ".join([cell for cell in row if cell])
                    if row_text:
                        content_lines.append(row_text)
            
            content = "\n".join(content_lines)
            return [{"page_number": 1, "content": content}]
        except Exception as e:
            logger.error(f"Error reading CSV {file_path}: {e}")
            raise

    def _extract_from_excel(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from Excel."""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas not installed. Cannot process Excel files.")
            raise ImportError("pandas is required for Excel processing")

        pages_content = []
        try:
            # Read all sheets
            xls = pd.ExcelFile(file_path)
            for i, sheet_name in enumerate(xls.sheet_names):
                # Load with header detection
                # Try to auto-detect header. If first row has many NaNs, maybe it's not the header.
                df = pd.read_excel(xls, sheet_name=sheet_name, header=0)
                
                # Check if header is valid (heuristic: < 50% "Unnamed")
                unnamed_cols = [c for c in df.columns if str(c).lower().startswith('unnamed')]
                if len(unnamed_cols) > len(df.columns) * 0.5:
                    # Likely no header, or header is further down.
                    # Try reloading with no header
                    df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                else:
                    # Clean headers
                    # Merge "Unnamed: 1" with previous column if it looks like a merged cell in logic,
                    # OR just replace Unnamed with empty string for MD table
                    new_cols = []
                    for c in df.columns:
                        col_str = str(c).strip()
                        if col_str.lower().startswith("unnamed"):
                            new_cols.append("")
                        else:
                             new_cols.append(col_str)
                    df.columns = new_cols

                # Convert to Markdown Table (Supported by most LLMs better than serialized rows)
                # Filter empty rows/cols
                df = df.dropna(how='all').dropna(axis=1, how='all')
                
                # Fill NaNs
                df = df.fillna("")
                
                if df.empty:
                    continue
                
                # Convert to Markdown Table in chunks to avoid memory spikes
                # Large Excel files (50k rows) create massive MD strings that choke the splitter/memory
                
                rows_per_chunk = 50
                total_rows = len(df)
                
                # If small enough, just do one chunk
                if total_rows <= rows_per_chunk:
                    md_table = df.to_markdown(index=False)
                    text = f"Sheet: {sheet_name}\n\n{md_table}"
                    pages_content.append({
                        "page_number": i + 1, 
                        "content": text
                    })
                else:
                    # Chunk it
                    for chunk_idx, start_row in enumerate(range(0, total_rows, rows_per_chunk)):
                        end_row = min(start_row + rows_per_chunk, total_rows)
                        chunk_df = df.iloc[start_row:end_row]
                        
                        if chunk_df.empty:
                            continue
                            
                        md_table = chunk_df.to_markdown(index=False)
                        # Each chunk gets context of which rows it contains
                        text = f"Sheet: {sheet_name} (Rows {start_row+1}-{end_row})\n\n{md_table}"
                        
                        pages_content.append({
                            # Use decimal page numbers to indicate sub-parts: 1.0, 1.1, etc.
                            # Or just sequential distinct items.
                            # Standard ingestion expects Page Number to be Int? 
                            # checking... existing code uses Int usually. 
                            # Let's use a float or just "1" and rely on chunking?
                            # The 'page_number' field is used for citation. "Page 1" is fine for all chunks of sheet 1?
                            # No, distinct is better. "Page 1 (Part 1)"
                            "page_number": i + 1, # Keep sheet as page number
                            "content": text
                        })
            return pages_content
        except Exception as e:
            logger.error(f"Error reading Excel {file_path}: {e}")
            raise

    def _is_text_garbage(self, text: str) -> bool:
        """
        Detects if text is likely PDF internal garbage or rendering noise.
        """
        if not text:
            return True
            
        # 1. PDF Internal Objects (The Zomato Issue)
        # Patterns like: /Pattern, /Shading, /Type, /Matrix, 4 0 R, obj, endobj
        pdf_garbage_markers = ["/Pattern", "/Shading", "/Type", "/Matrix", "/ColorSpace", "obj", "endobj", "stream"]
        garbage_hits = sum(1 for m in pdf_garbage_markers if m in text)
        if garbage_hits >= 2: # If multiple PDF keywords appear, it's definitely leakage
            return True
            
        # 2. Heuristics from _extract_text
        clean_t = " ".join([w for w in text.split() if not w.startswith(('http', 'www', 'ftp'))])
        if not clean_t.strip(): return False # URLs are fine
        
        # 3. Massive unknown token (Base64/Binary)
        if len(clean_t) > 80 and " " not in clean_t:
            return True
            
        # 4. Low valid density for long text
        if len(text) > 200:
             # Quick check for repeating characters (e.g. "VVVVVV")
             import re
             if re.search(r'(.)\1{4,}', clean_t): 
                 return True
                 
        return False

    async def _extract_pdf_pages_stream(self, file_path: str):
        """
        [Optimization] Async Generator yielding pages one by one for PDF Fast Path.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        
        # We wrap the blocking generator in an executor to yield control to the event loop
        # for each page processing step.
        
        chunks_iterator = self._pdf_page_generator_blocking(file_path)
        iter_obj = iter(chunks_iterator)
        
        # Helper to catch StopIteration safely outside the Future
        def safe_next(it):
            try:
                return next(it), False
            except StopIteration:
                return None, True

        while True:
            try:
                # Run safe_next in thread.
                page_data, is_done = await loop.run_in_executor(None, safe_next, iter_obj)
                if is_done:
                    break
                yield page_data
                
            except Exception as e:
                logger.error(f"Stream error: {e}")
                # We stop on error for now
                break

    def _pdf_page_generator_blocking(self, file_path: str):
        """Helper sync generator for pdfplumber running in thread"""
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                     # HEAVY LIFTING: extract_text
                     text = page.extract_text() or ""
                     
                     # [Deep Audit Fix] Garbage Check for PDF Internal Leakage
                     if self._is_text_garbage(text):
                         logger.warning(f"Page {i+1}: Text extraction returned garbage/metadata. Fallback to OCR.")
                         if self.settings.enable_ocr:
                             try:
                                 im = page.to_image(resolution=300).original
                                 import pytesseract
                                 text = pytesseract.image_to_string(im, timeout=60)
                                 # Re-check OCR result
                                 if self._is_text_garbage(text):
                                     logger.warning(f"Page {i+1}: OCR also returned garbage. Discarding.")
                                     text = ""
                             except Exception as e:
                                 logger.error(f"Page {i+1} OCR Fallback failed: {e}")
                                 text = ""
                         else:
                             text = ""

                     # Minimal cleanup
                     text = text.strip()
                     
                     yield {
                         "page_number": i + 1,
                         "content": text
                     }
        except Exception as e:
            logger.error(f"PDF Gen Error: {e}")
            raise

    
    def _extract_text_fast_wrapper(self, file_path: str, ext: str) -> List[Dict[str, Any]]:
        """
        [Dispatcher] Route file to appropriate extractor based on extension.
        """
        try:
            logger.info(f"Dispatching {ext} file: {file_path}")
            
            if ext == '.docx':
                return self._extract_from_docx(file_path)
            elif ext == '.txt':
                return self._extract_from_txt(file_path)
            elif ext == '.csv':
                return self._extract_from_csv(file_path)
            elif ext in ['.xls', '.xlsx']:
                return self._extract_from_excel(file_path)
            elif ext in ['.ppt', '.pptx']:
                return self._extract_from_ppt(file_path)
            elif ext in ['.png', '.jpg', '.jpeg']:
                return self._extract_from_image(file_path)
            else:
                logger.warning(f"No specific extractor for {ext}, attempting binary text scrape.")
                return self._scrape_binary_text(file_path)
                
        except Exception as e:
            logger.error(f"Fast extraction failed for {file_path}: {e}")
            return []

    def _scrape_binary_text(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Fallback: Extract printable strings from binary file.
        Useful for legacy .ppt or unknown formats.
        """
        try:
            import re
            min_len = 5
            found_strings = []
            
            with open(file_path, "rb") as f:
                content = f.read()
                # Find ASCII printable sequences length > 5
                # [\x20-\x7E] is standard ASCII printable range
                # We also allow newlines [\r\n]
                regex = rb"[\x20-\x7E\r\n]{" + str(min_len).encode() + rb",}"
                
                matches = re.finditer(regex, content)
                for m in matches:
                    s = m.group().decode('ascii', errors='ignore').strip()
                    if len(s) > min_len:
                        found_strings.append(s)
            
            text = "\n".join(found_strings)
            if not text: return []
            
            logger.info(f"Binary scrape extracted {len(text)} chars from {os.path.basename(file_path)}")
            return [{"page_number": 1, "content": text}]
            
        except Exception as e:
            logger.warning(f"Binary scrape failed: {e}")
            return []

    def _extract_from_ppt(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from PowerPoint (.pptx with .ppt fallback)."""
        ext = os.path.splitext(file_path)[1].lower()
        
        # 1. Try python-pptx (Best for .pptx)
        if ext == '.pptx':
            try:
                from pptx import Presentation
                pages_content = []
                prs = Presentation(file_path)
                
                for i, slide in enumerate(prs.slides):
                    slide_text = []
                    # Iterate through all shapes
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            slide_text.append(shape.text)
                    
                    full_text = "\n".join(slide_text)
                    if full_text.strip():
                         pages_content.append({
                            "page_number": i + 1,
                            "content": full_text
                        })
                logger.info(f"Extracted {len(pages_content)} slides from PPTX")
                return pages_content
            except Exception as e:
                logger.warning(f"python-pptx failed for {file_path}: {e}. Falling back to scraper.")

        # 2. Fallback: Binary String Scraper (For .ppt or failed .pptx)
        return self._scrape_binary_text(file_path)

    def _chunk_text(self, pages_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunk text using SemanticSplitter (Sentence-aware).
        """
        from app.document_processing.splitter import SemanticSplitter
        
        chunks = []
        # Use slightly larger chunks for semantic coherence
        splitter = SemanticSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap
        )
        
        for page in pages_content:
            text = page["content"]
            page_num = page["page_number"]
            
            logger.info(f"Chunking Page {page_num}: ContentLen={len(text)}")
            
            # Split text
            text_chunks = splitter.split_text(text)
            logger.info(f"Page {page_num} split into {len(text_chunks)} chunks")
            
            # Create chunk objects
            # Note: start_char and end_char are harder to track with recursive splitter
            # We'll approximate or scan for them if needed. 
            # For this implementation, scanning:
            
            current_pos = 0
            for chunk_text in text_chunks:
                # Find start char (simple approach, might fail with duplicates but good enough for now)
                start_char = text.find(chunk_text, current_pos)
                if start_char == -1:
                    start_char = current_pos # Fallback
                    
                end_char = start_char + len(chunk_text)
                
                chunks.append({
                    "content": chunk_text,
                    "page_number": page_num,
                    "start_char": start_char,
                    "end_char": end_char
                })
                
                # Move pos forward, but account for overlap potentially
                # Since find searches from current_pos, we sort of handle it.
                # To be robust with overlap, current_pos should advance by (length - overlap)
                current_pos = max(0, end_char - self.settings.chunk_overlap)
                    
        return chunks

    async def delete_document(self, document_id: int):
        """
        Delete document data: Vectors from Vector Store.
        Critical for avoiding ghost chunks.
        """
        try:
            logger.info(f"Deleting resources for document {document_id}")
            # Get chunks BEFORE the document is deleted from DB (otherwise cascade might remove them)
            # This DB call is synchronous, so we offload it
            import asyncio
            loop = asyncio.get_running_loop()
            
            chunks = await loop.run_in_executor(None, self.chunk_repo.get_by_document_id, document_id)
            chunk_ids = [c.id for c in chunks]
            
            if chunk_ids and self.vector_store:
                logger.info(f"Deleting {len(chunk_ids)} vectors.")
                await self.vector_store.delete_vectors(chunk_ids)
            else:
                logger.warning(f"No chunks found for doc {document_id} or vector store missing (count: {len(chunk_ids)})")
        except Exception as e:
            logger.error(f"Error deleting vectors for {document_id}: {e}")
            # Don't raise, as DB delete should proceed

                
        except Exception as e:
             logger.error(f"Error deleting vectors for doc {document_id}: {e}")
             # We catch error to ensure DB delete still happens in caller

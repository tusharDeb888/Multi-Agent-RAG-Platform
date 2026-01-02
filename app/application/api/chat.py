"""
Chat API endpoints.
"""
from typing import Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel
from loguru import logger

from app.domain.models import User
from app.application.api import deps
from app.application.services.rag_service import RAGService
from app.application.services.audit_service import AuditService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

class ChatRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5

class ChatResponse(BaseModel):
    answer: str
    citations: list
    metadata: dict

@router.post("/query", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_query(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(deps.get_current_user),
    rag_service: RAGService = Depends(deps.get_rag_service),
    audit_service: AuditService = Depends(deps.get_audit_service)
) -> Any:
    """
    Query the knowledge base using RAG.
    """
    try:
        # Execute query
        logger.debug("Calling rag_service.query")
        result = await rag_service.query(
            user_id=current_user.id,
            query=body.query,
            top_k=body.top_k
        )
        logger.debug("rag_service.query returned")
        
        # Log audit
        logger.debug("Calling audit_service.log_query")
        audit_service.log_query(
            user_id=current_user.id,
            query_text=body.query,
            response_text=result["answer"],
            accessed_document_ids=[c["document_id"] for c in result["citations"]]
        )
        logger.debug("audit_service.log_query returned")
        
        return {
            "answer": result["answer"],
            "citations": result["citations"],
            "metadata": {
                "chunks_retrieved": result.get("chunks_retrieved", 0),
                "chunks_after_filtering": result.get("chunks_after_filtering", 0),
                "model_name": result.get("model_name", "unknown")
            }
        }
        
    except Exception as e:
        logger.error(f"Error in chat_query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream")
@limiter.limit("20/minute")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(deps.get_current_user),
    rag_service: RAGService = Depends(deps.get_rag_service),
    audit_service: AuditService = Depends(deps.get_audit_service)
) -> StreamingResponse:
    """
    Stream RAG response using SSE.
    """
    # Audit logging for streaming
    # We wrap the generator to capture the full response and valid citations
    async def stream_with_audit():
        full_response = []
        captured_citations = []
        
        try:
            async for chunk in rag_service.stream_query(
                user_id=current_user.id,
                query=body.query,
                top_k=body.top_k
            ):
                # Analyze chunk to capture data
                try:
                    import json
                    # The chunk is "data: {...}\n\n"
                    if chunk.startswith("data: "):
                        data_str = chunk[6:].strip()
                        if data_str != "[DONE]":
                            data = json.loads(data_str)
                            
                            if "token" in data:
                                full_response.append(data["token"])
                            
                            if "citations" in data:
                                captured_citations.extend(data["citations"])
                                
                except Exception:
                    # Ignore parsing errors, just pass through
                    pass
                
                yield chunk
            
            # Stream finished successfully
            # Construct full text
            response_text = "".join(full_response)
            accessed_ids = [c["document_id"] for c in captured_citations]
            
            # Log to Audit Service (using sync wrapper or ensure service handles it)
            # Since audit_log is synchronous db operation, we can call it directly
            # but ideally should be in threadpool if it blocks. 
            # audit_service uses sync session.
            audit_service.log_query(
                user_id=current_user.id,
                query_text=body.query,
                response_text=response_text,
                accessed_document_ids=accessed_ids
            )
            
        except Exception as e:
            logger.error(f"Stream interrupted: {e}")
            # Try to log partial if possible
            audit_service.log_query(
                user_id=current_user.id,
                query_text=body.query,
                response_text="".join(full_response) + f" [ERROR: {str(e)}]",
                accessed_document_ids=[]
            )
            # Re-raise to close stream to client
            raise e

    return StreamingResponse(
        stream_with_audit(),
        media_type="text/event-stream"
    )

class HistoryItem(BaseModel):
    query: str
    timestamp: datetime
    response_snippet: Optional[str]

@router.get("/history", response_model=List[HistoryItem])
async def get_history(
    limit: int = 50,
    current_user: User = Depends(deps.get_current_user),
    audit_service: AuditService = Depends(deps.get_audit_service)
) -> Any:
    """
    Get user chat history.
    """
    try:
        history = audit_service.get_user_history(current_user.id, limit)
        return [
            {
                "query": h.query_text,
                "timestamp": h.timestamp,
                "response_snippet": h.response_text[:200] + "..." if h.response_text and len(h.response_text) > 200 else h.response_text
            }
            for h in history
        ]
    except Exception as e:
        logger.error(f"Error retrieving history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

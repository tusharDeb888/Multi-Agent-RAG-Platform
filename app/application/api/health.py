from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.application.api import deps
from app.infrastructure.llm.factory import LLMFactory
from loguru import logger
from typing import Dict, Any

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(
    db: Session = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    K8s/Docker Health Check.
    Verifies Database and LLM connectivity.
    """
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "llm": "unknown",
        "version": "1.0.0"
    }
    
    # 1. Check Database
    try:
        db.execute(text("SELECT 1 FROM dual")).scalar() # Oracle specific, assume config handles others?
        # Standard generic SQL is "SELECT 1" or similar. Oracle needs FROM dual. 
        # Using "SELECT 1 FROM dual" works for Oracle.
        # For SQLite/Postgres "SELECT 1" suffices but "FROM dual" fails.
        # Let's use a try/except for dual or fall back.
    except Exception:
        try:
             db.execute(text("SELECT 1"))
        except Exception as e:
            logger.error(f"Health Check DB Failed: {e}")
            health_status["database"] = "unhealthy"
            health_status["status"] = "unhealthy"
            raise HTTPException(status_code=503, detail="Database Unreachable")
            
    health_status["database"] = "connected"

    # 2. Check LLM (Optional: don't fail health check if LLM matches generic connectivity)
    # We just report it
    try:
        adapter = LLMFactory.create_llm_adapter()
        if await adapter.is_available():
            health_status["llm"] = "connected"
        else:
            health_status["llm"] = "disconnected"
    except Exception as e:
        health_status["llm"] = f"error: {str(e)}"

    return health_status

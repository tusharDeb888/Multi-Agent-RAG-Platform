"""
Main application entry point.
"""
import uvicorn
import os
# Fix for macOS OpenMP conflict (FAISS vs Torch vs Scikit-learn)
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import get_settings
from app.core.database import engine, Base
from app.application.api import api_router

# Import for warmup
from app.infrastructure.llm.factory import LLMFactory
from app.application.api.deps import get_vector_store, get_embedding_service

settings = get_settings()

def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
    )

    # Initialize Rate Limiter
    limiter = Limiter(
        key_func=get_remote_address, 
        default_limits=["100/minute"],
        storage_uri=settings.redis_url
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    
    # Set CORS
    origins = [str(origin).rstrip("/") for origin in settings.backend_cors_origins]
    logger.info(f"Configured CORS origins: {origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API router
    app.include_router(api_router, prefix=settings.api_prefix)
    
    @app.get("/")
    def root():
        """Root endpoint."""
        return {
            "message": f"Welcome to {settings.app_name}",
            "docs": f"{settings.api_prefix}/docs",
            "version": settings.app_version
        }
    
    # Event handlers
    @app.on_event("startup")
    async def startup_event():
        logger.info(f"Starting {settings.app_name}...")
        
        # Warmup AI components to prevent cold-start latency
        logger.info("Warming up AI Models (LLM, Embeddings, Vector Store)...")
        try:
            LLMFactory.warmup()
            get_embedding_service() # Initialize Singleton
            get_vector_store()      # Initialize Singleton
            logger.info("AI Models warmup complete.")
        except Exception as e:
            logger.error(f"AI Model warmup failed: {e}")

        # Create tables for development (use Alembic for production)
        if settings.is_development:
            logger.info("Creating database tables...")
            Base.metadata.create_all(bind=engine)
            
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info(f"Shutting down {settings.app_name}...")
        
    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

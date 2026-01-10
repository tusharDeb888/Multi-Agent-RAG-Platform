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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

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
        debug=settings.is_development
    )

    # Initialize Rate Limiter
    limiter = Limiter(
        key_func=get_remote_address, 
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.redis_url
    )
    app.state.limiter = limiter
    # Custom Rate Limit Handler to avoid AttributeErrors on ConnectionError
    def _robust_rate_limit_handler(request: Request, exc: Exception):
        # If Redis is down, slowapi might pass a ConnectionError here
        detail = getattr(exc, "detail", "Rate limit exceeded")
        # If it's a ConnectionError, it might not be a rate limit, but a backend failure
        if "ConnectionError" in type(exc).__name__:
            logger.error(f"Rate Limiter Backend Error: {exc}")
            # Fail open or closed? safely return 503 or 429
            # For now, let's treat it as 429 but invalid backend
            return _rate_limit_exceeded_handler(request, RateLimitExceeded(detail="System busy"))
            
        return _rate_limit_exceeded_handler(request, exc)

    app.add_exception_handler(RateLimitExceeded, _robust_rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
    
    # Set CORS
    # Explicitly parse/validate origins to ensure no malformed strings
    origins = settings.backend_cors_origins
    # Ensure they are strings (Pydantic might return AnyHttpUrl objects)
    origins = [str(o).rstrip("/") for o in origins]
    
    logger.info(f"🔒 Enforcing CORS Policy. Allowed Origins: {origins}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Diagnostic Middleware: Log Origin for Debugging
    @app.middleware("http")
    async def log_origin_middleware(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin:
            logger.debug(f"Incoming Request Origin: {origin}")
        return await call_next(request)

    
    # Include API router
    app.include_router(api_router, prefix=settings.api_prefix)
    
    # Serve React Frontend (Production)
    frontend_dist = "frontend/dist"
    
    if os.path.exists(frontend_dist):
        logger.info(f"Serving frontend from {frontend_dist}")
        
        # Mount assets
        app.mount("/assets", StaticFiles(directory=f"{frontend_dist}/assets"), name="assets")
        
        # Catch-all for SPA handling
        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            # Allow API routes to pass through (handled by api_router if matched, but if 404, we check prefix)
            if full_path.startswith("api"):
                from fastapi.exceptions import HTTPException
                raise HTTPException(status_code=404, detail="Not Found")
            
            # Serve index.html for client-side routing
            return FileResponse(f"{frontend_dist}/index.html")
    else:
        # Fallback root endpoint if frontend not built
        @app.get("/")
        def root():
            """Root endpoint."""
            return {
                "message": f"Welcome to {settings.app_name} (API Only mode)",
                "docs": f"{settings.api_prefix}/docs",
                "version": settings.app_version,
                "note": "Run 'npm run build' in frontend/ to serve UI."
            }
    
    # Event handlers
    @app.on_event("startup")
    async def startup_event():
        logger.info(f"Starting {settings.app_name}...")
        
        # Warmup AI components to prevent cold-start latency
        # In DEVELOPMENT, we skip warmup to save RAM/Time (Lazy Loading)
        if not settings.is_development:
            logger.info("Warming up AI Models (LLM, Embeddings, Vector Store)...")
            # Retry loop for initial service availability (Wait up to 30s)
            import asyncio
            from app.application.services.recovery_service import RecoveryService # Import here to avoid circular deps at top
            
            # 1. Warmup AI Models
            max_retries = 5
            for i in range(max_retries):
                try:
                    await LLMFactory.warmup()
                    get_embedding_service() # Initialize Singleton (Sync init, internal thread pools)
                    get_vector_store()      # Initialize Singleton (Sync init)
                    logger.info("AI Models warmup complete.")
                    break
                except Exception as e:
                    logger.warning(f"AI Model warmup failed (Attempt {i+1}/{max_retries}): {e}")
                    if i < max_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        logger.error("AI Model warmup failed after max retries. App may be degraded.")
                        
            # 2. Recover Stuck Documents (After AI services are ready)
            await RecoveryService.recover_stuck_documents()

        else:
            logger.info("Development Mode: Skipping AI Model warmup (Lazy Loading enabled).")


        # Create tables for development (use Alembic for production)
        if settings.is_development:
            logger.info("Creating database tables...")
            Base.metadata.create_all(bind=engine)
            
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info(f"Shutting down {settings.app_name}...")
        await LLMFactory.shutdown()
        
    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

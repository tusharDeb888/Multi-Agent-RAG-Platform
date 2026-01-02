"""
Logging configuration.
Follows Single Responsibility Principle - only handles logging setup.
"""
import sys
from loguru import logger
from app.core.config import get_settings


def setup_logging() -> None:
    """Configure application logging."""
    settings = get_settings()
    
    # Remove default handler
    logger.remove()
    
    # Add console handler with formatting
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level=settings.log_level,
        colorize=True
    )
    
    # Add file handler for production
    if settings.is_production:
        logger.add(
            "logs/app_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            level=settings.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            compression="zip"
        )
    
    logger.info(f"Logging configured for {settings.environment} environment")





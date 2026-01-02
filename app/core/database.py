"""
Database connection and session management.
Follows Single Responsibility Principle - only handles database connections.
"""
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool
from app.core.config import get_settings

settings = get_settings()

# Create base class for models
Base = declarative_base()

# Create engine with connection pooling
connect_args = {}
if "sqlite" in settings.database_url:
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.oracle_pool_size,
    max_overflow=settings.oracle_max_overflow,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.is_development,  # Log SQL in development
    future=True,
    connect_args=connect_args
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection for database sessions.
    Follows Dependency Inversion Principle - depends on abstraction.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(engine, "connect")
def set_oracle_encoding(dbapi_conn, connection_record):
    """Set Oracle encoding on connection."""
    if "oracle" in settings.database_url:
        cursor = dbapi_conn.cursor()
        cursor.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'")
        cursor.close()





"""
Domain models representing core business entities.
Follows Domain-Driven Design principles.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, 
    ForeignKey, Float, Enum as SQLEnum, Identity, Table,
    UniqueConstraint, Index, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base


# Association Table for Document-Department (Many-to-Many)
document_departments = Table(
    "document_departments",
    Base.metadata,
    Column("document_id", Integer, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True)
)


class Department(Base):
    """Department domain model."""
    __tablename__ = "departments"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    users = relationship("User", back_populates="department")
    documents = relationship("Document", secondary=document_departments, back_populates="departments")



class UserRole(str, Enum):
    """User role enumeration."""
    SUPER_ADMIN = "super_admin"
    DEPARTMENT_ADMIN = "department_admin"
    EMPLOYEE = "employee"
    AUDITOR = "auditor"


class DocumentStatus(str, Enum):
    """Document processing status."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    EXTRACTING = "EXTRACTING"   # OCR / Text Extraction
    CHUNKING = "CHUNKING"       # Splitting text
    EMBEDDING = "EMBEDDING"     # Generating vectors
    INDEXING = "INDEXING"       # Saving to Vector Store / DB
    PARTIAL = "PARTIAL"         # Some chunks indexed, search available but incomplete
    SEARCHABLE = "SEARCHABLE"   # Fully indexed and ready
    COMPLETED = "COMPLETED"     # Legacy/Done
    FAILED = "FAILED"


class ClassificationLevel(str, Enum):
    """Document classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AccessType(str, Enum):
    """Access control permission types."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"


class AuditAction(str, Enum):
    """Audit log action types."""
    LOGIN = "login"
    LOGOUT = "logout"
    QUERY = "query"
    UPLOAD = "upload"
    DELETE = "delete"
    ACCESS = "access"
    UPDATE = "update"
    FAILED_LOGIN = "failed_login"



class User(Base):
    """User domain model."""
    __tablename__ = "users"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    # department = Column(String(100), nullable=False) # Deprecated
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True) # Nullable for transition/superadmins without dept

    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)  # Soft Delete
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    
    # Security Clearance
    clearance_level = Column(SQLEnum(ClassificationLevel), default=ClassificationLevel.INTERNAL)
    
    # Relationships
    roles = relationship("UserRoleMap", foreign_keys="UserRoleMap.user_id", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    department = relationship("Department", back_populates="users")



class Role(Base):
    """Role domain model."""
    __tablename__ = "roles"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user_roles = relationship("UserRoleMap", back_populates="role")


class UserRoleMap(Base):
    """User-Role mapping (many-to-many)."""
    __tablename__ = "user_role_map"
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
    )
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="roles")
    role = relationship("Role", back_populates="user_roles")


class Document(Base):
    """Document domain model."""
    """Document domain model."""
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint('content_hash', name='uq_document_content_hash'),
        UniqueConstraint('file_path', name='uq_document_file_path'),
    )
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size_mb = Column(Float, nullable=False)
    mime_type = Column(String(100), nullable=False)
    total_pages = Column(Integer, default=0)
    title = Column(String(255), nullable=True)
    # department_id = Column(Integer, ForeignKey("departments.id"), nullable=True) # Replaced by M2M

    classification = Column(SQLEnum(ClassificationLevel), default=ClassificationLevel.INTERNAL)
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # [Fix] Explicit Python default to avoid ORA-01400 if DB default is missing
    uploaded_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON string for flexible metadata
    parser_version = Column(String(50), default="v1.0")  # Track pipeline version (e.g. "v1_recursive")
    
    # Deduplication
    content_hash = Column(String(64), nullable=True)
    
    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    access_policies = relationship("DocumentAccessPolicy", back_populates="document", cascade="all, delete-orphan")
    departments = relationship("Department", secondary=document_departments, back_populates="documents")



class DocumentChunk(Base):
    """Document chunk domain model for vectorization."""
    """Document chunk domain model for vectorization."""
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
        UniqueConstraint('vector_id', name='uq_chunk_vector_id'),
    )
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)  # Order within document
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA-256 hash
    page_number = Column(Integer, nullable=True)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    vector_id = Column(String(255), nullable=True)  # Reference to vector index
    metadata_json = Column(Text, nullable=True)  # JSON string for flexible metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    access_policies = relationship("ChunkAccessPolicy", back_populates="chunk", cascade="all, delete-orphan")


class DocumentAccessPolicy(Base):
    """Document-level access control."""
    __tablename__ = "document_access_policies"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True, index=True)
    # department = Column(String(100), nullable=True)  # Deprecated
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    access_type = Column(SQLEnum(AccessType), default=AccessType.READ, nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="access_policies")


class ChunkAccessPolicy(Base):
    """Chunk-level access control (for fine-grained permissions)."""
    __tablename__ = "chunk_access_policies"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True, index=True)
    # department = Column(String(100), nullable=True) # Deprecated
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    chunk = relationship("DocumentChunk", back_populates="access_policies")


class AuditLog(Base):
    """Audit log for compliance and security."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index('idx_audit_user_timestamp', 'user_id', 'timestamp'),
    )
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username_snapshot = Column(String(255), nullable=True)  # Snapshot key if user is deleted
    action = Column(SQLEnum(AuditAction), nullable=False)
    resource_type = Column(String(50), nullable=False)  # document, chunk, user, etc.
    resource_id = Column(Integer, nullable=True, index=True)
    query_text = Column(Text, nullable=True)  # For query actions
    response_text = Column(Text, nullable=True)  # For query responses
    accessed_documents = Column(Text, nullable=True)  # JSON array of document IDs
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")





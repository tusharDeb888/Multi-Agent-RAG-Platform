"""
Domain models representing core business entities.
Follows Domain-Driven Design principles.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, 
    ForeignKey, Float, LargeBinary, Enum as SQLEnum, Identity, Table
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
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
    PENDING = "pending"
    PROCESSING = "processing"
    PARTIAL = "partial"         # Some chunks indexed, search available but incomplete
    SEARCHABLE = "searchable"   # Fully indexed and ready
    COMPLETED = "completed"     # Legacy/Done
    FAILED = "failed"


class ClassificationLevel(str, Enum):
    """Document classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class User(Base):
    """User domain model."""
    __tablename__ = "users"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    # department = Column(String(100), nullable=False) # Deprecated
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True) # Nullable for transition/superadmins without dept

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user_roles = relationship("UserRoleMap", back_populates="role")


class UserRoleMap(Base):
    """User-Role mapping (many-to-many)."""
    __tablename__ = "user_role_map"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="roles")
    role = relationship("Role", back_populates="user_roles")


class Document(Base):
    """Document domain model."""
    __tablename__ = "documents"
    
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
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON string for flexible metadata
    
    # Deduplication
    content_hash = Column(String(64), index=True, nullable=True)
    
    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    access_policies = relationship("DocumentAccessPolicy", back_populates="document", cascade="all, delete-orphan")
    departments = relationship("Department", secondary=document_departments, back_populates="documents")



class DocumentChunk(Base):
    """Document chunk domain model for vectorization."""
    __tablename__ = "document_chunks"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Order within document
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA-256 hash
    page_number = Column(Integer, nullable=True)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    vector_id = Column(String(100), nullable=True)  # Reference to vector index
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    access_policies = relationship("ChunkAccessPolicy", back_populates="chunk", cascade="all, delete-orphan")


class DocumentAccessPolicy(Base):
    """Document-level access control."""
    __tablename__ = "document_access_policies"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True)
    # department = Column(String(100), nullable=True)  # Deprecated
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    access_type = Column(String(20), default="read", nullable=False)  # read, write, delete
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="access_policies")


class ChunkAccessPolicy(Base):
    """Chunk-level access control (for fine-grained permissions)."""
    __tablename__ = "chunk_access_policies"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True)
    # department = Column(String(100), nullable=True) # Deprecated
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    chunk = relationship("DocumentChunk", back_populates="access_policies")


class AuditLog(Base):
    """Audit log for compliance and security."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, Identity(start=1), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(100), nullable=False)  # query, upload, delete, access, etc.
    resource_type = Column(String(50), nullable=False)  # document, chunk, user, etc.
    resource_id = Column(Integer, nullable=True)
    query_text = Column(Text, nullable=True)  # For query actions
    response_text = Column(Text, nullable=True)  # For query responses
    accessed_documents = Column(Text, nullable=True)  # JSON array of document IDs
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")





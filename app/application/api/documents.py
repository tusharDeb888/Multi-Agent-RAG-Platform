"""
Document management API endpoints.
"""
import os
import shutil
from typing import List, Any, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from loguru import logger

from app.core.config import get_settings
from app.domain.models import User, Document, DocumentStatus, ClassificationLevel, UserRole, Department
from app.domain.repositories.document_repository import DocumentRepository

from app.application.api import deps
from app.application.services.ingestion_service import IngestionService
from pydantic import BaseModel

class DocumentUpdate(BaseModel):
    departments: List[str]

router = APIRouter()
settings = get_settings()

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    classification: ClassificationLevel = ClassificationLevel.INTERNAL,
    title: Optional[str] = Form(None),
    departments: str = Form("[]"), # JSON string list of department names
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    ingestion_service: IngestionService = Depends(deps.get_ingestion_service)
) -> Any:
    """
    Upload a document for ingestion.
    The document is saved to disk and processed asynchronously.
    """
    from starlette.concurrency import run_in_threadpool

    ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.xlsx', '.xls', '.csv'}
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {ALLOWED_EXTENSIONS}")
    
    # Check permissions
    # Note: Accessing relationships works because db session is active but we must be careful with lazy loads in async
    # Since deps.get_current_user returns a User object attached to session, simple access is usually OK if session open.
    # But ideally validation should be sync or carefully managed.
    allowed_roles = [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN, UserRole.EMPLOYEE]
    user_roles = [r.role.name for r in current_user.roles]
    
    if not any(role in allowed_roles for role in user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only administrators can upload documents"
        )
        
    # Create file path
    # [Security Fix] Sanitize filename to prevent path traversal
    safe_filename = os.path.basename(file.filename)
    file_location = os.path.join(UPLOAD_DIR, f"{current_user.id}_{safe_filename}")
    
    # 1. Security Hardening: MIME Validation
    from app.core.scanner import FileValidator, MalwareScanner
    
    # Read first 2KB for Magic Number detection
    header_bytes = await file.read(2048)
    await file.seek(0) # Reset pointer
    
    is_valid_mime, detected_type = FileValidator.validate_mime_type(header_bytes, safe_filename)
    if not is_valid_mime:
        raise HTTPException(
            status_code=400, 
            detail=f"Security Alert: File type mismatch. Detected {detected_type} for extension {ext}"
        )
    
    
    # 3. Compute Hash for Deduplication
    import hashlib
    sha256_hash = hashlib.sha256()
    
    # We already read 2048 bytes. Feed them to hash.
    sha256_hash.update(header_bytes)
    
    # Read rest of file in chunks
    file.file.seek(2048) # Resume from where we left off (or seek(0) if we want simpler logic but double read 2KB)
    # Actually simpler: Seek 0 and read all in chunks to avoid misses
    await file.seek(0)
    
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        sha256_hash.update(chunk)
        
    content_hash = sha256_hash.hexdigest()
    await file.seek(0) # IMPORTANT: Reset pointer for saving!
    
    # Check DB for duplicate (BLOCKING call wrapping)
    doc_repo = DocumentRepository(db)
    
    def check_duplicate_sync():
        return doc_repo.get_by_hash(content_hash)
        
    existing_doc = await run_in_threadpool(check_duplicate_sync)
    
    if existing_doc:
        # CONFLICT: File already exists
        return {
            "id": existing_doc.id,
            "filename": existing_doc.filename,
            "status": existing_doc.status,
            "message": f"Duplicate ignored. File already exists (ID: {existing_doc.id}).",
            "duplicate": True
        }

    # Save file (Non-Blocking)
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        
        def write_file_sync():
            with open(file_location, "wb+") as file_object:
                shutil.copyfileobj(file.file, file_object)
                
        # Offload blocking I/O to thread pool
        await loop.run_in_executor(None, write_file_sync)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")
        
    # 2. Security Hardening: Malware Scan (Stub)
    is_safe = MalwareScanner.scan_file(file_location)
    if not is_safe:
        os.remove(file_location) # Quaranatine/Delete
        raise HTTPException(status_code=400, detail="Security Alert: Malware detected in file.")
    
        
    # Get file size
    file_size = os.path.getsize(file_location) / (1024 * 1024) # MB
    
    # Prepare create logic (BLOCKING DB OPS)
    def create_document_sync():
        # Resolve Departments
        try:
            dept_names = json.loads(departments)
            if isinstance(dept_names, str):
                dept_names = [dept_names] # Handle single string
        except:
            dept_names = [departments.strip()] # Fallback to raw string
            
        if not dept_names:
            dept_names = ["General"]
            
        dept_objs = []
        for d_name in dept_names:
            d = db.query(Department).filter(Department.name == d_name).first()
            if not d:
                d = Department(name=d_name, description="Auto-created")
                db.add(d)
                db.commit()
                db.refresh(d)
            dept_objs.append(d)
            
        document = Document(
            filename=file.filename,
            original_filename=file.filename,
            title=title or file.filename,  # Use title if provided
            file_path=file_location,
            file_size_mb=file_size,
            mime_type=file.content_type or "application/pdf",
            # department_id=dept_obj.id, # REMOVED
            classification=classification,
            status=DocumentStatus.PENDING,
            uploaded_by=current_user.id,
            content_hash=content_hash
        )
        
        # Associate M2M
        document.departments = dept_objs

        doc_repo.add(document)
        db.commit()
        db.refresh(document)
        return document

    # Run DB creation in threadpool
    document = await run_in_threadpool(create_document_sync)
    
    # Trigger background processing using FastAPI BackgroundTasks
    background_tasks.add_task(ingestion_service.process_document, document.id)
    
    return {
        "id": document.id,
        "filename": document.filename,
        "status": document.status.lower(),
        "message": "Document uploaded and queued for processing"
    }

@router.get("/", response_model=List[dict])
def list_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    List all documents visible to the user.
    """
    doc_repo = DocumentRepository(db)

    # Check for Admin Roles
    is_admin = any(role.role.name in [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN] for role in current_user.roles)
    
    if is_admin:
        # Admins see ALL documents (as requested)
        documents = doc_repo.get_all(skip=skip, limit=limit)
    else:
        # Non-admins see ONLY documents in their department
        # Assuming user has a single department linking via department_id
        if current_user.department:
            documents = doc_repo.get_by_department(current_user.department.name)
            # Apply pagination manually if repo returns all (since get_by_department returns .all())
            # For better performance, repo method should accept skip/limit, but for now we slice list
            documents = documents[skip : skip + limit]
        else:
            # User has no department? Return General documents only.
            documents = doc_repo.get_by_department("General")
    
    return [
        {
            "id": doc.id,
            "title": doc.title or doc.filename,
            "filename": doc.filename,
            "status": doc.status.lower(),
            "departments": [d.name for d in doc.departments] if doc.departments else [],
            "classification": doc.classification,
            "uploaded_at": doc.uploaded_at,
            "processed_at": doc.processed_at
        }
        for doc in documents
    ]

@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    Get document details.
    """
    doc_repo = DocumentRepository(db)
    document = doc_repo.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Check permissions (Enforce Department Isolation)
    is_admin = any(role.role.name in [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN] for role in current_user.roles)
    
    if not is_admin:
        # User must belong to one of the document's departments
        user_dept = current_user.department.name if current_user.department else None
        doc_depts = {d.name for d in document.departments}
        
        if "General" not in doc_depts and (not user_dept or user_dept not in doc_depts):
             logger.warning(f"Access Denied: User {current_user.username} ({user_dept}) tried to access Doc {document_id} ({doc_depts})")
             raise HTTPException(status_code=403, detail="Access denied to this document")
        
    return {
        "id": document.id,
        "title": document.title or document.filename,
        "filename": document.filename,
        "status": document.status.lower(),
        "departments": [d.name for d in document.departments] if document.departments else [],
        "classification": document.classification,
        "uploaded_at": document.uploaded_at,
        "processed_at": document.processed_at,
        "error_message": document.error_message,
        "total_pages": document.total_pages
    }

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    cache_service: Any = Depends(deps.get_cache_service),
    ingestion_service: IngestionService = Depends(deps.get_ingestion_service)
) -> None:
    """
    Delete a document and its associated data.
    Only Admins or the uploader can delete.
    """
    from starlette.concurrency import run_in_threadpool
    doc_repo = DocumentRepository(db)
    
    # DB Access (Blocking)
    def get_doc_sync():
        return doc_repo.get_by_id(document_id)
        
    document = await run_in_threadpool(get_doc_sync)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Check permissions - Lazy load safe? Need to be careful. use safe access in sync function
    # NOTE: current_user is already loaded.
    is_admin = any(role.role.name in [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN] for role in current_user.roles)
    is_uploader = document.uploaded_by == current_user.id
    
    if not (is_admin or is_uploader):
         raise HTTPException(status_code=403, detail="Not authorized to delete this document")
         
    # Delete file from disk (IO)
    if document.file_path and os.path.exists(document.file_path):
        try:
            # os.remove is blocking but very fast.
            await run_in_threadpool(os.remove, document.file_path)
        except OSError as e:
            # Log error but proceed to delete DB record
            pass
            
    # Delete Vectors (via Ingestion Service)
    # This is NOW Async
    await ingestion_service.delete_document(document_id)

    # Delete from DB (Blocking)
    def delete_db_sync():
        doc_repo.delete(document_id)
        db.commit()
    
    await run_in_threadpool(delete_db_sync)
    
    # INVALIDATE CACHE
    logger.info(f"Document {document_id} deleted. Invalidating query cache.")
    # Assuming delete_pattern uses threadpool internal
    # Actually wait, delete_pattern is sync or async? 
    # Current CacheService implementation has async wrappers but delete_pattern is likely sync.
    # Let's wrap it just in case if it's slow (Redis scan)
    if hasattr(cache_service, 'delete_pattern_async'):
        await cache_service.delete_pattern_async("query:*")
    else:
        # Fallback to threadpool
        await run_in_threadpool(cache_service.delete_pattern, "query:*")



@router.patch("/{document_id}")
def update_document(
    document_id: int,
    doc_in: DocumentUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    cache_service: Any = Depends(deps.get_cache_service)
) -> Any:
    """
    Update document metadata (e.g. departments).
    Only Admins can update.
    """
    doc_repo = DocumentRepository(db)
    document = doc_repo.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Check permissions
    allowed_roles = [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN]
    user_roles = [r.role.name for r in current_user.roles]
    
    if not any(role in allowed_roles for role in user_roles):
        raise HTTPException(status_code=403, detail="Not authorized to update this document")

    # Update Departments
    if doc_in.departments is not None:
        dept_names = doc_in.departments
        if not dept_names:
            dept_names = ["General"] # Default if cleared
            
        dept_objs = []
        for d_name in dept_names:
            d = db.query(Department).filter(Department.name == d_name).first()
            if not d:
                d = Department(name=d_name, description="Auto-created")
                db.add(d)
                db.commit()
                db.refresh(d)
            dept_objs.append(d)
        
        document.departments = dept_objs
        
        # INVALIDATE CACHE
        # Any change to departments affects visibility, so we must wipe query cache
        logger.info(f"Document {document_id} updated. Invalidating query cache.")
        cache_service.delete_pattern("query:*")
        
    db.commit()
    db.refresh(document)
    
    return {
        "id": document.id,
        "filename": document.filename,
        "departments": [d.name for d in document.departments],
        "message": "Document updated successfully"
    }

@router.get("/{document_id}/content")
@router.get("/{document_id}/content/{filename}")
def view_document_content(
    document_id: int,
    filename: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user_flexible)
) -> Any:
    """
    Serve the document file content inline.
    Useful for displaying in browser/iframe.
    """
    doc_repo = DocumentRepository(db)
    document = doc_repo.get_by_id(document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Check permissions (Enforce Department Isolation)
    is_admin = any(role.role.name in [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN] for role in current_user.roles)
    
    if not is_admin:
        user_dept = current_user.department.name if current_user.department else None
        doc_depts = {d.name for d in document.departments}
        
        if "General" not in doc_depts and (not user_dept or user_dept not in doc_depts):
             logger.warning(f"Access Denied: User {current_user.username} tried to view content of Doc {document_id}")
             raise HTTPException(status_code=403, detail="Access denied to this document")
        
    if not document.file_path or not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
        
    return FileResponse(
        document.file_path, 
        media_type=document.mime_type, 
        filename=document.filename,
        content_disposition_type="inline"
    )

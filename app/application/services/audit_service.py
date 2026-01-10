"""
Audit Service for compliance logging.
Follows Single Responsibility Principle - only handles audit logging.
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from loguru import logger

from app.domain.models import AuditLog
from app.core.config import get_settings


class AuditService:
    """
    Service for audit logging.
    Ensures all user actions are logged for compliance.
    """
    
    def __init__(self, db: Session):
        """
        Initialize audit service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.settings = get_settings()
    
    def log_query(
        self,
        user_id: int,
        query_text: str,
        response_text: str,
        accessed_document_ids: List[int],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Log a user query.
        
        Args:
            user_id: User ID
            query_text: Query text
            response_text: Response text
            accessed_document_ids: List of document IDs accessed
            ip_address: User IP address
            user_agent: User agent string
            
        Returns:
            Created audit log entry
        """
        if not self.settings.enable_audit_logging:
            return None
        
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action="query",
                resource_type="document",
                query_text=query_text,
                response_text=response_text,
                accessed_documents=str(accessed_document_ids),
                ip_address=ip_address,
                user_agent=user_agent,
                timestamp=datetime.utcnow()
            )
            
            self.db.add(audit_log)
            self.db.commit()
            self.db.refresh(audit_log)
            
            logger.debug(f"Audit log created for user {user_id} query")
            return audit_log
            
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
            self.db.rollback()
            raise
    
    async def log_query_async(
        self,
        user_id: int,
        query_text: str,
        response_text: str,
        accessed_document_ids: List[int],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[AuditLog]:
        """
        Log a user query asynchronously.
        Offloads synchronous DB I/O to a thread.
        """
        if not self.settings.enable_audit_logging:
            return None
            
        import asyncio
        loop = asyncio.get_running_loop()
        
        return await loop.run_in_executor(
            None, 
            self.log_query, 
            user_id, 
            query_text, 
            response_text, 
            accessed_document_ids, 
            ip_address, 
            user_agent
        )
    
    def log_document_access(
        self,
        user_id: int,
        document_id: int,
        action: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Log document access.
        
        Args:
            user_id: User ID
            document_id: Document ID
            action: Action type (upload, delete, view, etc.)
            ip_address: User IP address
            user_agent: User agent string
            
        Returns:
            Created audit log entry
        """
        if not self.settings.enable_audit_logging:
            return None
        
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type="document",
                resource_id=document_id,
                ip_address=ip_address,
                user_agent=user_agent,
                timestamp=datetime.utcnow()
            )
            
            self.db.add(audit_log)
            self.db.commit()
            self.db.refresh(audit_log)
            
            return audit_log
            
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
            self.db.rollback()
            raise
    
    def log_user_action(
        self,
        user_id: int,
        action: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Log a generic user action.
        
        Args:
            user_id: User ID
            action: Action type
            resource_type: Type of resource
            resource_id: Resource ID (optional)
            ip_address: User IP address
            user_agent: User agent string
            
        Returns:
            Created audit log entry
        """
        if not self.settings.enable_audit_logging:
            return None
        
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                timestamp=datetime.utcnow()
            )
            
            self.db.add(audit_log)
            self.db.commit()
            self.db.refresh(audit_log)
            
            return audit_log
            
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
            self.db.rollback()
            raise
    
    def get_user_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[AuditLog]:
        """
        Get user chat history.
        
        Args:
            user_id: User ID
            limit: Maximum number of entries to return
            
        Returns:
            List of audit logs for queries
        """
        return (
            self.db.query(AuditLog)
            .filter(
                AuditLog.user_id == user_id,
                AuditLog.action == "query"
            )
            .order_by(desc(AuditLog.timestamp))
            .limit(limit)
            .all()
        )





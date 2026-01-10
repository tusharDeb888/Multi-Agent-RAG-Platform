"""
User repository for data access.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from loguru import logger

from app.domain.models import User, UserRole, Department
from app.domain.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for user operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, User)
    
    def get_by_username(self, username: str, lock: bool = False) -> Optional[User]:
        """
        Get user by username.
        Use lock=True for 'Check-then-Insert' flows.
        """
        query = self.db.query(User).filter(User.username == username)
        if lock:
            query = query.with_for_update()
        return query.first()
    
    def get_by_email(self, email: str, lock: bool = False) -> Optional[User]:
        """
        Get user by email.
        Use lock=True for 'Check-then-Insert' flows.
        """
        query = self.db.query(User).filter(User.email == email)
        if lock:
            query = query.with_for_update()
        return query.first()
    
    def get_by_department(self, department_name: str, skip: int = 0, limit: int = 100) -> List[User]:
        """Get users by department name with pagination."""
        return self.db.query(User).join(User.department).filter(
            Department.name == department_name
        ).order_by(User.id.desc()).offset(skip).limit(limit).all()
    
    def get_active_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all active users with pagination."""
        return self.db.query(User).filter(
            User.is_active == True
        ).order_by(User.id.desc()).offset(skip).limit(limit).all()

    def add(self, entity: User) -> User:
        """
        Add a new user with duplicate checks.
        Locks checks to prevent concurrency race conditions.
        """
        # Check for existing username
        if self.get_by_username(entity.username, lock=True):
            error_msg = f"User with username {entity.username} already exists."
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        # Check for existing email
        if self.get_by_email(entity.email, lock=True):
            error_msg = f"User with email {entity.email} already exists."
            logger.error(error_msg)
            raise ValueError(error_msg)

        super().add(entity)
        self.db.flush()
        return entity

    def create(self, entity: User) -> User:
        """Disable inherited create to prevent accidental commits."""
        raise NotImplementedError("Use add() and commit externally.")

    def update(self, entity: User) -> User:
        """Disable inherited update to prevent accidental commits."""
        raise NotImplementedError("Manage updates via session and commit externally.")

    def delete(self, id: int) -> bool:
        """
        Delete a user by ID (Soft Delete).
        Sets is_deleted=True and is_active=False.
        Does NOT commit.
        """
        entity = self.get_by_id(id)
        if entity:
            entity.is_deleted = True
            entity.is_active = False
            # self.db.add(entity) # Not strictly needed if attached, but good practice
            logger.info(f"Soft-deleted user {id}")
            return True
        return False





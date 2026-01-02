"""
User repository for data access.
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from app.domain.models import User, UserRole, Department
from app.domain.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for user operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, User)
    
    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_by_department(self, department_name: str) -> List[User]:
        """Get users by department name."""
        return self.db.query(User).join(User.department).filter(Department.name == department_name).all()
    
    def get_active_users(self) -> List[User]:
        """Get all active users."""
        return self.db.query(User).filter(User.is_active == True).all()





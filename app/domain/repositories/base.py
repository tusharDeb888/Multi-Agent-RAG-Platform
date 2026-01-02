"""
Base repository interface.
Follows Repository Pattern and Dependency Inversion Principle.
"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List
from sqlalchemy.orm import Session

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository.
    Follows Single Responsibility Principle - only handles data access.
    """
    
    def __init__(self, db: Session, model_class: type):
        """
        Initialize repository.
        
        Args:
            db: Database session
            model_class: SQLAlchemy model class
        """
        self.db = db
        self.model_class = model_class
    
    def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID."""
        return self.db.query(self.model_class).filter(self.model_class.id == id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all entities with pagination."""
        return self.db.query(self.model_class).offset(skip).limit(limit).all()
    
    def add(self, entity: T) -> T:
        """Add an entity to the session without committing."""
        self.db.add(entity)
        return entity

    def create(self, entity: T) -> T:
        """Create a new entity."""
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity
    
    def update(self, entity: T) -> T:
        """Update an entity."""
        self.db.commit()
        self.db.refresh(entity)
        return entity
    
    def delete(self, id: int) -> bool:
        """Delete an entity by ID."""
        entity = self.get_by_id(id)
        if entity:
            self.db.delete(entity)
            self.db.commit()
            return True
        return False





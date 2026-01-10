from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from app.core.database import get_db
from app.application.api import deps
from app.domain.models import Department, User, UserRole

router = APIRouter()

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Department name")
    description: str | None = None
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty or whitespace only")
        return v.strip()

class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: str | None
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[DepartmentResponse])
def list_departments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    List all departments (Paginated).
    """
    return db.query(Department).offset(skip).limit(limit).all()

@router.post("/", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    dept_in: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    Create a new department.
    Only Admins can create departments.
    """
    # Check permissions
    allowed_roles = [UserRole.SUPER_ADMIN, UserRole.DEPARTMENT_ADMIN]
    user_roles = [r.role.name for r in current_user.roles]
    
    if not any(role in allowed_roles for role in user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only administrators can create departments"
        )
        
    try:
        # Check duplicate (Explicit check first for better UX)
        existing = db.query(Department).filter(Department.name == dept_in.name).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Department '{dept_in.name}' already exists"
            )
            
        dept = Department(
            name=dept_in.name,
            description=dept_in.description
        )
        db.add(dept)
        db.commit()
        db.refresh(dept)
        
        logger.info(f"Department '{dept.name}' created by user {current_user.id}")
        return dept
        
    except IntegrityError:
        db.rollback()
        logger.warning(f"Duplicate department creation attempt: {dept_in.name}")
        raise HTTPException(
            status_code=409,
            detail=f"Department '{dept_in.name}' already exists (Constraint Violation)"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating department: {e}")
        raise HTTPException(status_code=500, detail="Internal System Error")


from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.application.api import deps
from app.domain.models import Department, User, UserRole

router = APIRouter()

class DepartmentCreate(BaseModel):
    name: str
    description: str | None = None

class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: str | None
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[DepartmentResponse])
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    List all departments.
    """
    return db.query(Department).all()

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
        
    # Check duplicate
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
    
    return dept

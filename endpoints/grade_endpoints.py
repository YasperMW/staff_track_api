from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models.db_models import User, Grade
from timezone_config import get_current_time
from endpoints.auth_endpoints import get_current_user

router = APIRouter(prefix="/api/grades", tags=["grades"])

class CreateGradeRequest(BaseModel):
    name: str
    annual_leave_days: int = 21


class UpdateGradeRequest(BaseModel):
    name: Optional[str] = None
    annual_leave_days: Optional[int] = None


@router.post("")
async def create_grade(
    request: CreateGradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new grade. Only accessible by System Admins."""
    user_role = current_user.role.name.lower() if current_user.role else ""
    if 'system admin' not in user_role and 'system administrator' not in user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only System Admins can create grades"
        )
    
    existing = db.query(Grade).filter(Grade.name == request.name, Grade.deleted_at.is_(None)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grade with this name already exists"
        )
    
    grade = Grade(
        name=request.name,
        annual_leave_days=request.annual_leave_days,
        created_at=get_current_time(),
        updated_at=get_current_time()
    )
    db.add(grade)
    db.commit()
    db.refresh(grade)
    
    return {
        "id": str(grade.grade_id),
        "name": grade.name,
        "annual_leave_days": grade.annual_leave_days
    }


@router.put("/{grade_id}")
async def update_grade(
    grade_id: str,
    request: UpdateGradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    
    user_role = current_user.role.name.lower() if current_user.role else ""
    if 'system admin' not in user_role and 'system administrator' not in user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only System Admins can update grades"
        )
    
    grade = db.query(Grade).filter(Grade.grade_id == grade_id, Grade.deleted_at.is_(None)).first()
    if not grade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grade not found"
        )
    
    if request.name:
        existing = db.query(Grade).filter(Grade.name == request.name, Grade.deleted_at.is_(None), Grade.grade_id != grade_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grade with this name already exists"
            )
        grade.name = request.name
    
    if request.annual_leave_days is not None:
        grade.annual_leave_days = request.annual_leave_days
    
    grade.updated_at = get_current_time()
    db.commit()
    db.refresh(grade)
    
    return {
        "id": str(grade.grade_id),
        "name": grade.name,
        "annual_leave_days": grade.annual_leave_days
    }


@router.delete("/{grade_id}")
async def delete_grade(
    grade_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    
    user_role = current_user.role.name.lower() if current_user.role else ""
    if 'system admin' not in user_role and 'system administrator' not in user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only System Admins can delete grades"
        )
    
    grade = db.query(Grade).filter(Grade.grade_id == grade_id, Grade.deleted_at.is_(None)).first()
    if not grade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grade not found"
        )
    
    if grade.users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete grade that is assigned to users. Reassign users first."
        )
    
    grade.deleted_at = get_current_time()
    grade.deleted_by = current_user.user_id
    db.commit()
    
    return {"success": True}
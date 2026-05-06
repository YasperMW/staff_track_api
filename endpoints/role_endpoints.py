from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime

from database import get_db
from models.db_models import User, Role
from timezone_config import get_current_time
from endpoints.auth_endpoints import get_current_user

router = APIRouter(prefix="/roles", tags=["roles"])


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class RoleResponse(BaseModel):
    role_id: str
    name: str
    created_at: str
    updated_at: str
    user_count: int


def _verify_admin(current_user: User):
    allowed = ['System Admin', 'System Administrator', 'Principal Hospital Administrator']
    if not current_user.role or current_user.role.name not in allowed:
        raise HTTPException(status_code=403, detail="Only administrators can manage roles")


@router.get("/")
async def get_all_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all roles with user counts"""
    _verify_admin(current_user)
    
    roles = db.query(Role).filter(Role.deleted_at.is_(None)).all()
    
    result = []
    for role in roles:
        user_count = db.query(User).filter(
            User.role_id == role.role_id,
            User.deleted_at.is_(None)
        ).count()
        
        result.append({
            "role_id": str(role.role_id),
            "name": role.name,
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "updated_at": role.updated_at.isoformat() if role.updated_at else None,
            "user_count": user_count,
        })
    
    return {"roles": result, "total_count": len(result)}


@router.get("/{role_id}")
async def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single role by ID"""
    _verify_admin(current_user)
    
    try:
        role_uuid = UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role ID")
    
    role = db.query(Role).filter(Role.role_id == role_uuid, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    user_count = db.query(User).filter(
        User.role_id == role.role_id,
        User.deleted_at.is_(None)
    ).count()
    
    return {
        "role_id": str(role.role_id),
        "name": role.name,
        "created_at": role.created_at.isoformat() if role.created_at else None,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        "user_count": user_count,
    }


@router.post("/")
async def create_role(
    request: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new role"""
    _verify_admin(current_user)
    
    existing = db.query(Role).filter(
        Role.name == request.name,
        Role.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role already exists")
    
    now = get_current_time()
    new_role = Role(
        name=request.name,
        created_at=now,
        updated_at=now,
    )
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    
    return {
        "role_id": str(new_role.role_id),
        "name": new_role.name,
        "created_at": new_role.created_at.isoformat() if new_role.created_at else None,
        "updated_at": new_role.updated_at.isoformat() if new_role.updated_at else None,
        "user_count": 0,
    }


@router.put("/{role_id}")
async def update_role(
    role_id: str,
    request: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing role"""
    _verify_admin(current_user)
    
    try:
        role_uuid = UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role ID")
    
    role = db.query(Role).filter(Role.role_id == role_uuid, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    if request.name:
        existing = db.query(Role).filter(
            Role.name == request.name,
            Role.role_id != role_uuid,
            Role.deleted_at.is_(None)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Role name already exists")
        role.name = request.name
    
    role.updated_at = get_current_time()
    db.commit()
    db.refresh(role)
    
    user_count = db.query(User).filter(
        User.role_id == role.role_id,
        User.deleted_at.is_(None)
    ).count()
    
    return {
        "role_id": str(role.role_id),
        "name": role.name,
        "created_at": role.created_at.isoformat() if role.created_at else None,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        "user_count": user_count,
    }


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Soft delete a role"""
    _verify_admin(current_user)
    
    try:
        role_uuid = UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role ID")
    
    role = db.query(Role).filter(Role.role_id == role_uuid, Role.deleted_at.is_(None)).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    user_count = db.query(User).filter(
        User.role_id == role.role_id,
        User.deleted_at.is_(None)
    ).count()
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete role: {user_count} user(s) still have this role"
        )
    
    role.deleted_at = get_current_time()
    role.deleted_by = current_user.user_id
    role.updated_at = get_current_time()
    db.commit()
    
    return {"message": "Role deleted successfully"}

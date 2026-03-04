from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, Role, Department, LeaveBalance
from datetime import datetime

router = APIRouter(prefix="/api/leave/policies", tags=["leave"])

class LeavePolicyItem(BaseModel):
    role_name: Optional[str] = None
    department_name: Optional[str] = None
    leave_type: str
    allocated_days: int
    bonus_days: int = 0

@router.get("", response_model=List[LeavePolicyItem])
async def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Simple derivation from balances of sample users (placeholder implementation)
    rows = db.execute("""
        SELECT r.name as role_name, d.name as department_name, lb.leave_type, MAX(lb.allocated_days) as allocated_days, MAX(lb.bonus_days) as bonus_days
        FROM leave_balances lb
        JOIN users u ON u.user_id = lb.user_id
        LEFT JOIN roles r ON r.role_id = u.role_id
        LEFT JOIN departments d ON d.department_id = u.department_id
        GROUP BY r.name, d.name, lb.leave_type
    """).fetchall()
    return [
        LeavePolicyItem(
            role_name=row[0],
            department_name=row[1],
            leave_type=row[2],
            allocated_days=int(row[3] or 0),
            bonus_days=int(row[4] or 0),
        ) for row in rows
    ]

class UpsertPolicyRequest(BaseModel):
    leave_type: str
    allocated_days: int
    bonus_days: int = 0
    role_name: Optional[str] = None
    department_name: Optional[str] = None

@router.post("/apply")
async def apply_policy(
    payload: UpsertPolicyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find cohort
    query = db.query(User).filter(User.deleted_at.is_(None))
    if payload.role_name:
        role = db.query(Role).filter(Role.name == payload.role_name).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        query = query.filter(User.role_id == role.role_id)
    if payload.department_name:
        dept = db.query(Department).filter(Department.name == payload.department_name).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        query = query.filter(User.department_id == dept.department_id)
    users = query.all()
    # Apply to balances
    for u in users:
        lb = db.query(LeaveBalance).filter(LeaveBalance.user_id == u.user_id, LeaveBalance.leave_type == payload.leave_type).first()
        if not lb:
            lb = LeaveBalance(
                user_id=u.user_id,
                leave_type=payload.leave_type,
                allocated_days=payload.allocated_days,
                bonus_days=payload.bonus_days,
                used_days=0,
                remaining_days=max(payload.allocated_days + payload.bonus_days, 0),
                updated_at=datetime.utcnow(),
            )
            db.add(lb)
        else:
            lb.allocated_days = payload.allocated_days
            lb.bonus_days = payload.bonus_days
            total = (lb.allocated_days or 0) + (lb.bonus_days or 0)
            used = lb.used_days or 0
            lb.remaining_days = max(total - used, 0)
            lb.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "affected_users": len(users)}

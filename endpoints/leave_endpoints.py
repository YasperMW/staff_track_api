from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, LeaveBalance
from datetime import datetime

router = APIRouter(prefix="/leave", tags=["leave"])

class LeaveBalanceResponse(BaseModel):
    leave_type: str
    allocated_days: int
    used_days: int
    bonus_days: int
    remaining_days: int
    updated_at: str

@router.get("/balances", response_model=List[LeaveBalanceResponse])
async def get_my_leave_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    balances = db.query(LeaveBalance).filter(LeaveBalance.user_id == current_user.user_id).all()
    return [
        LeaveBalanceResponse(
            leave_type=b.leave_type,
            allocated_days=b.allocated_days or 0,
            used_days=b.used_days or 0,
            bonus_days=b.bonus_days or 0,
            remaining_days=b.remaining_days or 0,
            updated_at=b.updated_at.isoformat() if b.updated_at else datetime.utcnow().isoformat()
        )
        for b in balances
    ]

class LeaveAllocateRequest(BaseModel):
    leave_type: str
    allocated_days: int
    bonus_days: int = 0

@router.post("/allocate")
async def allocate_leave(
    payload: LeaveAllocateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    b = db.query(LeaveBalance).filter(
        LeaveBalance.user_id == current_user.user_id,
        LeaveBalance.leave_type == payload.leave_type
    ).first()
    if not b:
        b = LeaveBalance(
            user_id=current_user.user_id,
            leave_type=payload.leave_type,
            allocated_days=payload.allocated_days,
            bonus_days=payload.bonus_days,
            used_days=0,
            remaining_days=max(payload.allocated_days + payload.bonus_days, 0),
            updated_at=datetime.utcnow()
        )
        db.add(b)
    else:
        b.allocated_days = payload.allocated_days
        b.bonus_days = payload.bonus_days
        total = (b.allocated_days or 0) + (b.bonus_days or 0)
        used = b.used_days or 0
        b.remaining_days = max(total - used, 0)
        b.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}

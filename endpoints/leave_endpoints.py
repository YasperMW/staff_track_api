from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, LeaveBalance, Notification
from datetime import datetime
from fcm_service import send_push_notification

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
            allocated_days=int(b.allocated_days or 0),
            used_days=int(b.used_days or 0),
            bonus_days=int(b.bonus_days or 0),
            remaining_days=int(b.remaining_days or 0),
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

    # Send notifications about balance update
    total_days = (payload.allocated_days or 0) + (payload.bonus_days or 0)

    # Create in-app notification
    notification = Notification(
        user_id=current_user.user_id,
        title="Leave Balance Updated",
        message=f"Your {payload.leave_type.replace('_', ' ').title()} leave balance has been updated to {total_days} days",
        type="leave_balance_update",
        is_read=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()

    # Send push notification
    if current_user.fcm_tokens:
        for token_record in current_user.fcm_tokens:
            try:
                await send_push_notification(
                    token=token_record.fcm_token,
                    title="Leave Balance Updated",
                    body=f"Your {payload.leave_type.replace('_', ' ').title()} leave balance has been updated to {total_days} days",
                    data={
                        "type": "leave_balance_update",
                        "leave_type": payload.leave_type,
                        "total_days": total_days
                    }
                )
            except Exception as e:
                print(f"Failed to send push notification: {e}")

    return {"success": True}

from datetime import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.db_models import User, Notification, UserFCMToken
from endpoints.auth_endpoints import get_current_user
from fcm_service import send_push_notification

router = APIRouter(tags=["notifications"])

class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str
    recipient_user_id: Optional[str] = None

class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    is_read: bool
    created_at: str
    updated_at: str

class TokenRegistration(BaseModel):
    fcm_token: str
    device_id: Optional[str] = None

@router.post("/register-token", response_model=dict)
async def register_fcm_token(
    registration: TokenRegistration,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Register or update an FCM token for the current user"""
    
    # Check if token already exists for this user
    existing_token = db.query(UserFCMToken).filter(
        UserFCMToken.fcm_token == registration.fcm_token
    ).first()
    
    if existing_token:
        if existing_token.user_id != current_user.user_id:
            # Token transferred to another user
            existing_token.user_id = current_user.user_id
            existing_token.updated_at = datetime.now()
        else:
            # Token already belongs to this user, just update timestamp
            existing_token.updated_at = datetime.now()
    else:
        # Create new token record
        new_token = UserFCMToken(
            user_id=current_user.user_id,
            fcm_token=registration.fcm_token,
            device_id=registration.device_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_token)
    
    db.commit()
    return {"message": "FCM token registered successfully"}

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user notifications"""
    
    query = db.query(Notification).filter(Notification.user_id == current_user.user_id)
    
    if unread_only:
        query = query.filter(Notification.is_read == False)
    
    notifications = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()
    
    return [
        NotificationResponse(
            id=str(notification.notification_id),
            title=notification.title,
            message=notification.message,
            type=notification.type,
            is_read=notification.is_read,
            created_at=notification.created_at.isoformat(),
            updated_at=notification.updated_at.isoformat()
        )
        for notification in notifications
    ]

@router.post("/", response_model=NotificationResponse)
async def create_notification(
    notification: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new notification"""
    
    # Only admins can create notifications for other users
    if notification.recipient_user_id and current_user.role.name not in ['HR Admin', 'System Admin']:
        raise HTTPException(status_code=403, detail="Only admins can create notifications for other users")
    
    recipient_id = notification.recipient_user_id or current_user.user_id
    
    new_notification = Notification(
        user_id=recipient_id,
        title=notification.title,
        message=notification.message,
        type=notification.type,
        is_read=False,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    
    # Send push notification via FCM
    recipient_user = db.query(User).filter(User.user_id == recipient_id).first()
    if recipient_user and recipient_user.fcm_tokens:
        for fcm_token_record in recipient_user.fcm_tokens:
            await send_push_notification(
                token=fcm_token_record.fcm_token,
                title=notification.title,
                body=notification.message,
                data={
                    "notification_id": str(new_notification.notification_id),
                    "type": notification.type
                }
            )
    
    return NotificationResponse(
        id=str(new_notification.notification_id),
        title=new_notification.title,
        message=new_notification.message,
        type=new_notification.type,
        is_read=new_notification.is_read,
        created_at=new_notification.created_at.isoformat(),
        updated_at=new_notification.updated_at.isoformat()
    )

@router.put("/{notification_id}/read", response_model=dict)
async def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as read"""
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notification_id,
        Notification.user_id == current_user.user_id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    notification.updated_at = datetime.now()
    db.commit()
    
    return {"message": "Notification marked as read"}

@router.put("/mark-all-read", response_model=dict)
async def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all user notifications as read"""
    
    db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        Notification.is_read == False
    ).update({"is_read": True, "updated_at": datetime.now()})
    
    db.commit()
    
    return {"message": "All notifications marked as read"}

@router.get("/unread-count", response_model=dict)
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get count of unread notifications"""
    
    count = db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        Notification.is_read == False
    ).count()
    
    return {"unread_count": count}

@router.delete("/{notification_id}", response_model=dict)
async def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a notification"""
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notification_id,
        Notification.user_id == current_user.user_id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    db.delete(notification)
    db.commit()
    
    return {"message": "Notification deleted"}

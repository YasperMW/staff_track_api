from datetime import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.db_models import User, Notification, UserFCMToken
from endpoints.auth_endpoints import get_current_user
from fcm_service import send_push_notification, send_multicast_push_notification

router = APIRouter(tags=["notifications"])

class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str
    recipient_user_id: Optional[str] = None

class BroadcastNotification(BaseModel):
    title: str
    body: str
    notification_type: str  # app_update, maintenance, incident, general
    target: str = "all"  # all, department, role
    target_value: Optional[str] = None  # department name or role name if target is not all
    data: Optional[dict] = None

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

@router.post("/test-push", response_model=dict)
async def test_push_notification(
    title: str = "Test Notification",
    body: str = "This is a test notification from the backend",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test push notification for the current user"""
    try:
        # Get user's FCM tokens
        fcm_tokens = db.query(UserFCMToken).filter(UserFCMToken.user_id == current_user.user_id).all()
        
        if not fcm_tokens:
            return {"error": "No FCM tokens found for this user"}
        
        results = []
        for token_record in fcm_tokens:
            result = await send_push_notification(
                token=token_record.fcm_token,
                title=title,
                body=body,
                data={"test": "true", "timestamp": str(datetime.now())}
            )
            results.append({
                "token": token_record.fcm_token[:20] + "...",
                "result": result
            })
        
        return {
            "message": f"Test notifications sent to {len(results)} tokens",
            "results": results
        }
        
    except Exception as e:
        return {"error": f"Failed to send test notification: {str(e)}"}

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

@router.post("/broadcast", response_model=dict)
async def send_broadcast_notification(
    broadcast: BroadcastNotification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a broadcast notification to all users or a specific group.
    Only admins can send broadcast notifications.
    """
    # Check admin permissions
    admin_roles = ['HR Admin', 'System Admin', 'Principal Hospital Administrator', 'HR', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can send broadcast notifications"
        )

    # Get target users
    query = db.query(User).filter(User.deleted_at.is_(None), User.status == 'active')

    if broadcast.target == "department" and broadcast.target_value:
        query = query.join(User.department).filter(User.department.has(name=broadcast.target_value))
    elif broadcast.target == "role" and broadcast.target_value:
        query = query.join(User.role).filter(User.role.has(name=broadcast.target_value))

    users = query.all()

    if not users:
        return {"message": "No users found matching the target criteria", "sent_count": 0}

    # Collect all FCM tokens
    all_tokens = []
    for user in users:
        if user.fcm_tokens:
            for token_record in user.fcm_tokens:
                all_tokens.append(token_record.fcm_token)

    if not all_tokens:
        return {"message": "No FCM tokens found for target users", "sent_count": 0}

    # Prepare notification data
    notification_data = broadcast.data or {}
    notification_data["type"] = broadcast.notification_type
    notification_data["sent_at"] = datetime.now().isoformat()

    # Send multicast push notification
    result = await send_multicast_push_notification(
        tokens=all_tokens,
        title=broadcast.title,
        body=broadcast.body,
        data=notification_data,
        priority="high",
        notification_type=broadcast.notification_type
    )

    # Create in-app notifications for each user
    for user in users:
        new_notification = Notification(
            user_id=user.user_id,
            title=broadcast.title,
            message=broadcast.body,
            type=broadcast.notification_type,
            is_read=False,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_notification)

    db.commit()

    # Handle result (could be real Firebase response or mock response)
    if result is None:
        # Firebase not initialized or other critical error
        return {
            "message": "Push notification service unavailable. In-app notifications created.",
            "target_users": len(users),
            "tokens_targeted": len(all_tokens),
            "push_sent": 0,
            "push_failed": len(all_tokens),
            "in_app_created": len(users)
        }
    
    success_count = result.success_count if result else 0
    failure_count = result.failure_count if result else 0

    return {
        "message": f"Broadcast notification sent",
        "target_users": len(users),
        "tokens_targeted": len(all_tokens),
        "push_sent": success_count,
        "push_failed": failure_count,
        "in_app_created": len(users)
    }

@router.get("/broadcast/types", response_model=dict)
async def get_notification_types():
    """Get available notification types for broadcast"""
    return {
        "notification_types": [
            {"value": "app_update", "label": "App Update", "description": "Notify users about app updates"},
            {"value": "maintenance", "label": "Maintenance Alert", "description": "Scheduled or emergency maintenance notifications"},
            {"value": "incident", "label": "Incident Report", "description": "Important incident or safety alerts"},
            {"value": "general", "label": "General Announcement", "description": "General information for all users"}
        ],
        "targets": [
            {"value": "all", "label": "All Users"},
            {"value": "department", "label": "Specific Department"},
            {"value": "role", "label": "Specific Role"}
        ]
    }

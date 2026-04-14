from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, model_validator
from typing import List, Optional, Dict, Any
import os
import json
import firebase_admin
from firebase_admin import credentials, messaging
from firebase_admin.exceptions import FirebaseError
from sqlalchemy.orm import Session
from sqlalchemy import select, update, desc, and_, or_, func
from models import DeviceToken, User, Notification, NotificationRead, BroadcastLog
from database import get_db
from endpoints.admin import require_admin_user
import uuid
import logging
import asyncio
from datetime import date

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
try:
    # Get service account key from environment variable
    firebase_credentials = os.getenv('FIREBASE_CREDENTIALS')
    if not firebase_credentials:
        raise ValueError('FIREBASE_CREDENTIALS environment variable not set')
        
    # Parse the JSON string from environment variable
    cred_dict = json.loads(firebase_credentials)
    
    # Initialize the app with the service account credentials
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    logger.info('Firebase Admin SDK initialized successfully')
except Exception as e:
    logger.error(f'Error initializing Firebase Admin SDK: {str(e)}')
    raise

router = APIRouter(
    tags=['notifications']
)

# Pydantic models
class RegisterTokenRequest(BaseModel):
    user_id: str
    token: str
    platform: Optional[str] = 'android'  # or 'ios'

class NotificationPayload(BaseModel):
    user_ids: List[str]
    title: str
    body: str
    type: Optional[str] = "other"  # 'booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other'
    data: Optional[dict] = {}

class BroadcastNotificationRequest(BaseModel):
    title: str
    body: str
    notification_type: Optional[str] = "system"
    target_audience: Optional[str] = "all"
    data: Optional[dict] = None
    user_ids: Optional[List[str]] = None
    university: Optional[str] = None
    hostel_id: Optional[str] = None
    booking_status: Optional[List[str]] = None  # Filter by booking status: ['confirmed', 'active', 'pending', etc.]

class AdvancedBroadcastRequest(BaseModel):
    title: str
    body: str
    notification_type: Optional[str] = "system"
    data: Optional[dict] = None
    
    # Targeting options - choose one or more
    target_audience: Optional[str] = "all"  # 'all', 'students', 'landlords'
    specific_users: Optional[List[str]] = None  # Specific user IDs
    university_filter: Optional[str] = None  # University name for students
    hostel_filter: Optional[str] = None  # Hostel ID for students with bookings
    booking_status_filter: Optional[List[str]] = None  # Booking status filter
    user_type_filter: Optional[List[str]] = None  # Multiple user types
    
    @model_validator(mode='before')
    def validate_targeting(cls, data):
        if isinstance(data, dict):
            # Ensure at least one targeting option is specified
            has_targeting = (
                data.get('target_audience') and data.get('target_audience') != 'all' or
                data.get('specific_users') or
                data.get('university_filter') or
                data.get('hostel_filter') or
                data.get('booking_status_filter') or
                data.get('user_type_filter')
            )
            
            if not has_targeting:
                data['target_audience'] = 'all'
                
        return data

# Device token registration endpoint
@router.post('/register-token')
async def register_device_token(req: RegisterTokenRequest, db: Session = Depends(get_db)):
    # Parse user_id as UUID type
    try:
        user_id = uuid.UUID(req.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")
    
    # Check if user exists
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Upsert logic
    try:
        q = db.query(DeviceToken).filter(DeviceToken.user_id == user_id, DeviceToken.token == req.token).one_or_none()
        if q:
            # Update platform, updated_at
            q.platform = req.platform
            db.commit()
            return {"status": "Token updated", "user_id": req.user_id, "token": req.token}
        else:
            dt = DeviceToken(user_id=user_id, token=req.token, platform=req.platform)
            db.add(dt)
            db.commit()
            return {"status": "Token registered", "user_id": req.user_id, "token": req.token}
    except Exception as e:
        db.rollback()
        logger.error(f"Error registering device token for user {req.user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to register device token")

# Device token unregistration endpoint
@router.delete('/unregister-token')
async def unregister_device_token(req: RegisterTokenRequest, db: Session = Depends(get_db)):
    # Parse user_id as UUID type
    try:
        user_id = uuid.UUID(req.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")
    
    # Check if user exists
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Find and delete the device token
        q = db.query(DeviceToken).filter(DeviceToken.user_id == user_id, DeviceToken.token == req.token).one_or_none()
        if q:
            db.delete(q)
            db.commit()
            return {"status": "Token unregistered", "user_id": req.user_id, "token": req.token}
        else:
            return {"status": "Token not found", "user_id": req.user_id, "token": req.token}
    except Exception as e:
        db.rollback()
        logger.error(f"Error unregistering device token for user {req.user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to unregister device token")

# FCM sending utility using Firebase Admin SDK
async def send_fcm_push(token: str, title: str, body: str, data: Optional[dict] = None) -> Dict[str, Any]:
    """
    Send a push notification using Firebase Admin SDK
    
    Args:
        token: The FCM registration token of the target device
        title: Notification title
        body: Notification body
        data: Optional data payload
        
    Returns:
        Dict containing the message ID or error information
    """
    if not token:
        raise ValueError("Token cannot be empty")
        
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
        data=data or {},
    )
    
    try:
        # Run blocking Firebase call in a thread executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, messaging.send, message)
        logger.info(f"Successfully sent message: {response}")
        return {"success": True, "message_id": response, "status": "Message sent successfully"}
    except ValueError as e:
        logger.error(f"Invalid argument error: {e}")
        return {"success": False, "error": f"Invalid argument: {str(e)}", "status": "Failed to send message"}
    except FirebaseError as e:
        logger.error(f"Firebase error: {e}")
        return {"success": False, "error": f"Firebase error: {str(e)}", "status": "Failed to send message"}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"success": False, "error": f"Unexpected error: {str(e)}", "status": "Failed to send message"}

# Helper function to send notifications (can be imported by other modules)
async def send_notification_to_users(
    db: Session,
    user_ids: List[uuid.UUID],
    title: str,
    body: str,
    notification_type: str = "other",
    data: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Helper function to send notifications to multiple users and save them to the database.
    This function can be imported and used by other endpoints.
    
    Args:
        db: Database session
        user_ids: List of user UUIDs to send notifications to
        title: Notification title
        body: Notification body
        notification_type: Type of notification (booking, payment, message, etc.)
        data: Optional additional data payload
        
    Returns:
        Dict with status and counts
    """
    if not user_ids:
        return {"status": "skipped", "message": "No users to notify"}
    
    # Validate notification type
    valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
    notification_type = notification_type if notification_type in valid_types else 'other'
    
    # Get device tokens for all users
    tokens = db.query(DeviceToken).filter(DeviceToken.user_id.in_(user_ids)).all()
    
    if not tokens:
        logger.warning(f"No device tokens found for users: {user_ids}")
    
    # Prepare FCM data payload with type included
    # FCM requires all data values to be strings
    fcm_data = {}
    if data:
        for key, value in data.items():
            fcm_data[str(key)] = str(value) if value is not None else ""
    fcm_data['type'] = notification_type
    
    notifications_created = []
    fcm_responses = []
    
    try:
        # Map to store created notifications by user_id
        user_notification_map = {}

        # Create notification records in database for all users
        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                body=body,
                data=fcm_data,
                is_read=False
            )
            db.add(notification)
            # Store reference to notification object
            user_notification_map[user_id] = notification
            notifications_created.append(user_id)
        
        # Commit all notifications to database
        db.commit()
        
        # Refresh notifications to get the generated IDs
        for notif in user_notification_map.values():
            db.refresh(notif)
            
        logger.info(f"Created {len(notifications_created)} notification records in database")
        
        # Send FCM push notifications
        for t in tokens:
            try:
                # Create a copy of fcm_data for this user
                user_fcm_data = fcm_data.copy()
                
                # Add notification_id to the payload if available
                if t.user_id in user_notification_map:
                    user_fcm_data['notification_id'] = str(user_notification_map[t.user_id].notification_id)
                
                resp = await send_fcm_push(t.token, title, body, user_fcm_data)
                fcm_responses.append({"user_id": str(t.user_id), "result": resp})
            except Exception as e:
                logger.error(f"Error sending FCM to token {t.token}: {str(e)}")
                fcm_responses.append({"user_id": str(t.user_id), "error": str(e)})
        
        return {
            "status": "success",
            "notifications_saved": len(notifications_created),
            "fcm_sent": len([r for r in fcm_responses if r.get("result", {}).get("success")]),
            "fcm_responses": fcm_responses
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error in send_notification_to_users: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "notifications_saved": 0
        }


# Push notification trigger endpoint
@router.post('/send')
async def send_notification(payload: NotificationPayload, db: Session = Depends(get_db)):
    # Parse UUIDs, skip bad ones
    parsed_user_ids = []
    for uid in payload.user_ids:
        try:
            parsed_user_ids.append(uuid.UUID(uid))
        except Exception:
            continue
    
    if not parsed_user_ids:
        raise HTTPException(status_code=400, detail="No valid user_ids provided")
    
    # Use the helper function
    result = await send_notification_to_users(
        db=db,
        user_ids=parsed_user_ids,
        title=payload.title,
        body=payload.body,
        notification_type=payload.type,
        data=payload.data
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=f"Error sending notifications: {result.get('error')}")
    
    return {
        "status": "done",
        "notifications_saved": result["notifications_saved"],
        "fcm_responses": result["fcm_responses"]
    }

# ============================================
# Admin Notification Endpoints
# ============================================

@router.get('/users')
async def get_users(
    user_type: Optional[str] = Query(None, description="Filter by user type: 'tenant', 'landlord', 'admin'"),
    university: Optional[str] = Query(None, description="Filter by university"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get list of users for admin targeting interface.
    Admin-only endpoint for fetching users to select for notifications.
    
    Args:
        user_type: Filter by user type (optional)
        university: Filter by university (optional)
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)
        
    Returns:
        Dict with users list and total count
    """
    try:
        # Build query
        query = db.query(User)
        
        # Apply filters
        if user_type:
            valid_types = ['tenant', 'landlord', 'admin']
            if user_type not in valid_types:
                raise HTTPException(status_code=400, detail=f"Invalid user_type. Must be one of: {valid_types}")
            query = query.filter(User.user_type == user_type)
        
        if university:
            query = query.filter(User.university.ilike(f"%{university}%"))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination and ordering
        users = query.order_by(User.first_name, User.last_name).offset(offset).limit(limit).all()
        
        # Convert to response format
        user_list = []
        for user in users:
            user_data = {
                "user_id": str(user.user_id),
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "email": user.email,
                "user_type": user.user_type,
                "university": user.university,
                "phone": user.phone_number,
                "is_verified": user.is_verified,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
            user_list.append(user_data)
        
        return {
            "users": user_list,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch users")


# ============================================
# Broadcast Log Endpoints (Audit)
# ============================================

@router.get('/broadcast-logs')
async def get_broadcast_logs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    broadcast_type: Optional[str] = Query(None, description="Filter by broadcast type: 'simple' or 'advanced'"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of broadcast logs for audit purposes.
    Admin-only endpoint.
    """
    try:
        query = db.query(BroadcastLog).order_by(BroadcastLog.created_at.desc())

        # Apply filters
        if broadcast_type:
            query = query.filter(BroadcastLog.broadcast_type == broadcast_type)
        if notification_type:
            query = query.filter(BroadcastLog.notification_type == notification_type)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * per_page
        logs = query.offset(offset).limit(per_page).all()

        return {
            "broadcasts": [
                {
                    "broadcast_id": str(log.broadcast_id),
                    "broadcast_type": log.broadcast_type,
                    "title": log.title,
                    "body": log.body[:200] + "..." if len(log.body) > 200 else log.body,  # Truncate body for list view
                    "notification_type": log.notification_type,
                    "target_audience": log.target_audience,
                    "targeting_criteria": log.targeting_criteria,
                    "recipients_summary": log.recipients_summary,
                    "fcm_sent": log.fcm_sent,
                    "fcm_failed": log.fcm_failed,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "created_by": str(log.created_by) if log.created_by else None
                }
                for log in logs
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching broadcast logs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch broadcast logs")


@router.get('/broadcast-logs/{broadcast_id}')
async def get_broadcast_log(
    broadcast_id: str,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed broadcast log by ID including full FCM responses.
    Admin-only endpoint.
    """
    try:
        try:
            broadcast_uuid = uuid.UUID(broadcast_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid broadcast ID format")

        log = db.query(BroadcastLog).filter(BroadcastLog.broadcast_id == broadcast_uuid).first()

        if not log:
            raise HTTPException(status_code=404, detail="Broadcast log not found")

        return {
            "broadcast_id": str(log.broadcast_id),
            "broadcast_type": log.broadcast_type,
            "title": log.title,
            "body": log.body,
            "notification_type": log.notification_type,
            "target_audience": log.target_audience,
            "targeting_criteria": log.targeting_criteria,
            "recipients_summary": log.recipients_summary,
            "fcm_sent": log.fcm_sent,
            "fcm_failed": log.fcm_failed,
            "fcm_responses": log.fcm_responses,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "created_by": str(log.created_by) if log.created_by else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching broadcast log: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch broadcast log")

# ============================================
# Notification Management Endpoints
# ============================================

@router.get('', response_model=Dict[str, Any])
async def get_notifications(
    user_id: str = Query(..., description="User ID to fetch notifications for"),
    is_read: Optional[bool] = Query(None, description="Filter by read status (true/false)"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of notifications to return"),
    offset: int = Query(0, ge=0, description="Number of notifications to skip"),
    db: Session = Depends(get_db)
):
    """
    Get notifications for a user with optional filtering and pagination.
    
    Query Parameters:
    - user_id: Required. The user ID to fetch notifications for
    - is_read: Optional. Filter by read status (true/false)
    - type: Optional. Filter by notification type (booking, message, payment, etc.)
    - limit: Optional. Maximum number of notifications (default: 50, max: 100)
    - offset: Optional. Number of notifications to skip for pagination (default: 0)
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")
    
    # Verify user exists
    user = db.query(User).filter(User.user_id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build query - ensure we only get notifications for this specific user
    query = db.query(Notification).filter(Notification.user_id == user_uuid)
    
    # Apply filters
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)
    
    if type:
        valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
        if type in valid_types:
            query = query.filter(Notification.type == type)
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply ordering (newest first) and pagination
    notifications = query.order_by(desc(Notification.created_at)).offset(offset).limit(limit).all()
    
    # Get unread count
    unread_count = db.query(Notification).filter(
        Notification.user_id == user_uuid,
        Notification.is_read == False
    ).count()
    
    # Convert SQLAlchemy objects to dictionaries before validation
    notification_dicts = [{
        'notification_id': n.notification_id,
        'user_id': n.user_id,
        'type': n.type,
        'title': n.title,
        'body': n.body,
        'data': n.data or {},
        'is_read': n.is_read,
        'created_at': n.created_at
    } for n in notifications]
    
    return {
        "notifications": [NotificationRead.model_validate(n).model_dump() for n in notification_dicts],
        "total": total_count,
        "unread_count": unread_count,
        "limit": limit,
        "offset": offset
    }


@router.get('/{notification_id}', response_model=NotificationRead)
async def get_notification(
    notification_id: str,
    user_id: str = Query(..., description="User ID to verify ownership"),
    db: Session = Depends(get_db)
):
    """
    Get a specific notification by ID.
    Verifies that the notification belongs to the specified user.
    """
    try:
        notif_uuid = uuid.UUID(notification_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notif_uuid,
        Notification.user_id == user_uuid
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return NotificationRead.model_validate(notification)


@router.put('/{notification_id}/read', response_model=NotificationRead)
async def mark_notification_read(
    notification_id: str,
    user_id: str = Query(..., description="User ID to verify ownership"),
    db: Session = Depends(get_db)
):
    """
    Mark a specific notification as read.
    Verifies that the notification belongs to the specified user.
    """
    try:
        notif_uuid = uuid.UUID(notification_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notif_uuid,
        Notification.user_id == user_uuid
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    
    logger.info(f"Marked notification {notification_id} as read for user {user_id}")
    return NotificationRead.model_validate(notification)


@router.put('/read-all', response_model=Dict[str, Any])
async def mark_all_notifications_read(
    user_id: str = Query(..., description="User ID to mark all notifications as read"),
    type: Optional[str] = Query(None, description="Optional: Only mark notifications of this type as read"),
    db: Session = Depends(get_db)
):
    """
    Mark all notifications as read for a user.
    Optionally filter by notification type.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")
    
    # Build query
    query = db.query(Notification).filter(
        Notification.user_id == user_uuid,
        Notification.is_read == False
    )
    
    # Apply type filter if provided
    if type:
        valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
        if type in valid_types:
            query = query.filter(Notification.type == type)
    
    # Update all matching notifications
    updated_count = query.update({"is_read": True}, synchronize_session=False)
    db.commit()
    
    logger.info(f"Marked {updated_count} notifications as read for user {user_id}")
    return {
        "status": "success",
        "updated_count": updated_count,
        "message": f"Marked {updated_count} notification(s) as read"
    }


@router.delete('/{notification_id}', response_model=Dict[str, str])
async def delete_notification(
    notification_id: str,
    user_id: str = Query(..., description="User ID to verify ownership"),
    db: Session = Depends(get_db)
):
    """
    Delete a specific notification.
    Verifies that the notification belongs to the specified user.
    """
    try:
        notif_uuid = uuid.UUID(notification_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notif_uuid,
        Notification.user_id == user_uuid
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    db.delete(notification)
    db.commit()
    
    logger.info(f"Deleted notification {notification_id} for user {user_id}")
    return {
        "status": "success",
        "message": "Notification deleted successfully"
    }


@router.delete('', response_model=Dict[str, Any])
async def delete_notifications(
    user_id: str = Query(..., description="User ID to delete notifications for"),
    is_read: Optional[bool] = Query(None, description="Optional: Only delete read/unread notifications"),
    type: Optional[str] = Query(None, description="Optional: Only delete notifications of this type"),
    delete_all: bool = Query(False, description="If true, delete all notifications (ignores other filters)"),
    db: Session = Depends(get_db)
):
    """
    Delete notifications for a user with optional filtering.
    
    Query Parameters:
    - user_id: Required. The user ID to delete notifications for
    - is_read: Optional. Only delete read (true) or unread (false) notifications
    - type: Optional. Only delete notifications of this type
    - delete_all: Optional. If true, delete all notifications (default: false)
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")
    
    # Build query
    if delete_all:
        query = db.query(Notification).filter(Notification.user_id == user_uuid)
    else:
        query = db.query(Notification).filter(Notification.user_id == user_uuid)
        
        # Apply filters
        if is_read is not None:
            query = query.filter(Notification.is_read == is_read)
        
        if type:
            valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
            if type in valid_types:
                query = query.filter(Notification.type == type)
    
    # Get count before deletion
    deleted_count = query.count()
    
    # Delete notifications
    query.delete(synchronize_session=False)
    db.commit()
    
    logger.info(f"Deleted {deleted_count} notification(s) for user {user_id}")
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} notification(s)"
    }


@router.get('/stats/summary', response_model=Dict[str, Any])
async def get_notification_stats(
    user_id: str = Query(..., description="User ID to get notification statistics for"),
    db: Session = Depends(get_db)
):
    """
    Get notification statistics for a user.
    Returns counts by type and read status.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")
    
    # Get total count
    total_count = db.query(Notification).filter(Notification.user_id == user_uuid).count()
    
    # Get unread count
    unread_count = db.query(Notification).filter(
        Notification.user_id == user_uuid,
        Notification.is_read == False
    ).count()
    
    # Get counts by type
    type_counts = {}
    valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
    for notif_type in valid_types:
        count = db.query(Notification).filter(
            Notification.user_id == user_uuid,
            Notification.type == notif_type
        ).count()
        if count > 0:
            type_counts[notif_type] = count
    
    return {
        "user_id": user_id,
        "total_count": total_count,
        "unread_count": unread_count,
        "read_count": total_count - unread_count,
        "type_counts": type_counts
    }


# ============================================
# Admin Notification Endpoints
# ============================================

@router.post('/broadcast')
async def broadcast_notification(
    payload: Optional[BroadcastNotificationRequest] = Body(None),
    title: Optional[str] = Query(None, description="Notification title"),
    body: Optional[str] = Query(None, description="Notification body"),
    notification_type: Optional[str] = Query(None, description="Notification type"),
    target_audience: Optional[str] = Query(None, description="Target audience: 'all', 'students', 'landlords'"),
    db: Session = Depends(get_db)
):
    """
    Send notification to users with FCM tokens, optionally filtered by user type.
    Admin-only endpoint for broadcasting system-wide notifications.
    NOTE: This endpoint does NOT store notifications in the database - it only sends FCM pushes.
    
    Args:
        title: Notification title
        body: Notification body
        notification_type: Type of notification (booking, message, payment, maintenance, review, system, other)
        target_audience: Target audience ('all', 'students', 'landlords')
        data: Optional additional data payload
        
    Returns:
        Dict with status, recipient breakdown, and FCM response details
    """
    try:
        if payload is not None:
            title = payload.title
            body = payload.body
            notification_type = payload.notification_type or "system"
            target_audience = payload.target_audience or "all"
            data = payload.data
            requested_user_ids = payload.user_ids
            university = payload.university
            hostel_id = payload.hostel_id
            booking_status = payload.booking_status
        else:
            data = None
            requested_user_ids = None
            university = None
            hostel_id = None
            booking_status = None

        if not title or not body:
            raise HTTPException(status_code=422, detail="title and body are required")

        notification_type = notification_type or "system"
        target_audience = target_audience or "all"

        # Validate target audience
        valid_audiences = ['all', 'students', 'landlords']
        if target_audience not in valid_audiences:
            raise HTTPException(status_code=400, detail=f"Invalid target_audience. Must be one of: {valid_audiences}")

        if university and target_audience != 'students':
            raise HTTPException(status_code=400, detail="university filter is only supported for target_audience='students'")

        if hostel_id and target_audience != 'students':
            raise HTTPException(status_code=400, detail="hostel_id filter is only supported for target_audience='students'")

        parsed_requested_user_ids: Optional[List[uuid.UUID]] = None
        if requested_user_ids:
            parsed_requested_user_ids = []
            for uid in requested_user_ids:
                try:
                    parsed_requested_user_ids.append(uuid.UUID(uid))
                except Exception:
                    continue

            if not parsed_requested_user_ids:
                raise HTTPException(status_code=400, detail="No valid user_ids provided")

        parsed_hostel_id: Optional[uuid.UUID] = None
        if hostel_id:
            try:
                parsed_hostel_id = uuid.UUID(hostel_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid hostel_id UUID")
        
        # Build query based on target audience
        # We include User so we can return user names in the detailed results
        query = db.query(DeviceToken, User).join(User, DeviceToken.user_id == User.user_id)
        
        if target_audience == 'students':
            query = query.filter(User.user_type == 'tenant')
        elif target_audience == 'landlords':
            query = query.filter(User.user_type == 'landlord')
        # 'all' doesn't need additional filtering

        if parsed_requested_user_ids:
            query = query.filter(User.user_id.in_(parsed_requested_user_ids))

        if university:
            query = query.filter(User.university.isnot(None)).filter(User.university.ilike(university))

        if parsed_hostel_id:
            # Current booking means:
            # - booking status in confirmed/active (or specified status)
            # - today within [start_date, end_date]
            # - booking.student_id is a real user (exclude enrolled_student_id-only bookings)
            from models import Booking as BookingModel, Room as RoomModel
            today = date.today()
            
            # Default booking statuses if not specified
            status_filter = booking_status or ["confirmed", "active"]
            
            student_ids_subq = (
                db.query(BookingModel.student_id)
                .join(RoomModel, BookingModel.room_id == RoomModel.room_id)
                .filter(RoomModel.hostel_id == parsed_hostel_id)
                .filter(BookingModel.student_id.isnot(None))
                .filter(BookingModel.start_date <= today)
                .filter(BookingModel.end_date >= today)
                .filter(func.lower(BookingModel.status).in_([s.lower() for s in status_filter]))
                .distinct()
                .subquery()
            )
            query = query.filter(User.user_id.in_(select(student_ids_subq.c.student_id)))
        
        rows = query.all()
        
        if not rows:
            logger.warning(f"No device tokens found for target audience: {target_audience}")
            return {"status": "skipped", "message": f"No device tokens found for target audience: {target_audience}"}
        
        # Count recipients by type
        student_count = len([1 for (_, u) in rows if getattr(u, 'user_type', None) == 'tenant'])
        landlord_count = len([1 for (_, u) in rows if getattr(u, 'user_type', None) == 'landlord'])
        
        # Get all user IDs from tokens
        user_ids = [dt.user_id for (dt, _) in rows]
        
        # Validate notification type
        valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
        notification_type = notification_type if notification_type in valid_types else 'system'
        
        # Prepare FCM data payload with type included
        fcm_data = {}
        if data:
            for key, value in data.items():
                fcm_data[str(key)] = str(value) if value is not None else ""
        fcm_data['type'] = notification_type
        
        fcm_responses = []
        
        logger.info(f"Broadcasting notification to {len(rows)} users (target: {target_audience})")
        
        # Send FCM push notifications directly (no database storage)
        for (dt, u) in rows:
            try:
                resp = await send_fcm_push(dt.token, title, body, fcm_data)
                fcm_responses.append({
                    "user_id": str(dt.user_id),
                    "user_type": getattr(u, 'user_type', 'unknown'),
                    "first_name": getattr(u, 'first_name', None),
                    "last_name": getattr(u, 'last_name', None),
                    "full_name": (f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}").strip() or None,
                    "result": resp
                })
            except Exception as e:
                logger.error(f"Error sending FCM to token {dt.token}: {str(e)}")
                fcm_responses.append({
                    "user_id": str(dt.user_id),
                    "user_type": getattr(u, 'user_type', 'unknown'),
                    "first_name": getattr(u, 'first_name', None),
                    "last_name": getattr(u, 'last_name', None),
                    "full_name": (f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}").strip() or None,
                    "error": str(e)
                })
        
        # Calculate success counts by user type
        student_success = len([r for r in fcm_responses if r.get("user_type") == 'tenant' and r.get("result", {}).get("success")])
        landlord_success = len([r for r in fcm_responses if r.get("user_type") == 'landlord' and r.get("result", {}).get("success")])
        student_failed = len([r for r in fcm_responses if r.get("user_type") == 'tenant' and not r.get("result", {}).get("success")])
        landlord_failed = len([r for r in fcm_responses if r.get("user_type") == 'landlord' and not r.get("result", {}).get("success")])

        fcm_sent = len([r for r in fcm_responses if r.get("result", {}).get("success")])
        fcm_failed_count = len([r for r in fcm_responses if not r.get("result", {}).get("success")])

        # Create broadcast log for audit
        try:
            broadcast_log = BroadcastLog(
                broadcast_type='simple',
                title=title,
                body=body,
                notification_type=notification_type,
                target_audience=target_audience,
                recipients_summary={
                    "students": {"total": student_count, "sent": student_success, "failed": student_failed},
                    "landlords": {"total": landlord_count, "sent": landlord_success, "failed": landlord_failed}
                },
                fcm_sent=fcm_sent,
                fcm_failed=fcm_failed_count,
                fcm_responses=fcm_responses
            )
            db.add(broadcast_log)
            db.commit()
            logger.info(f"Broadcast log created: {broadcast_log.broadcast_id}")
        except Exception as log_error:
            logger.error(f"Failed to create broadcast log: {str(log_error)}")
            # Don't fail the request if logging fails
            db.rollback()

        return {
            "status": "success",
            "message": f"Broadcast notification sent to {len(rows)} users",
            "target_audience": target_audience,
            "recipients": {
                "total": len(rows),
                "students": {
                    "total": student_count,
                    "sent": student_success,
                    "failed": student_failed
                },
                "landlords": {
                    "total": landlord_count,
                    "sent": landlord_success,
                    "failed": landlord_failed
                }
            },
            "fcm_sent": fcm_sent,
            "fcm_failed": fcm_failed_count,
            "fcm_responses": fcm_responses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in broadcast_notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/broadcast-advanced')
async def advanced_broadcast_notification(
    payload: AdvancedBroadcastRequest,
    db: Session = Depends(get_db)
):
    """
    Advanced broadcast notification with enhanced targeting options.
    Supports multiple filtering criteria and complex targeting logic.
    
    Args:
        payload: AdvancedBroadcastRequest with enhanced targeting options
        
    Returns:
        Dict with status, recipient breakdown, and FCM response details
    """
    try:
        title = payload.title
        body = payload.body
        notification_type = payload.notification_type or "system"
        data = payload.data
        
        if not title or not body:
            raise HTTPException(status_code=422, detail="title and body are required")

        # Validate notification type
        valid_types = ['booking', 'message', 'payment', 'maintenance', 'review', 'system', 'other']
        notification_type = notification_type if notification_type in valid_types else 'system'

        # Build query based on targeting options
        query = db.query(DeviceToken, User).join(User, DeviceToken.user_id == User.user_id)
        
        # Apply user type filters
        if payload.user_type_filter:
            # Support multiple user types
            valid_user_types = ['tenant', 'landlord', 'admin']
            filtered_types = [ut for ut in payload.user_type_filter if ut in valid_user_types]
            if filtered_types:
                query = query.filter(User.user_type.in_(filtered_types))
        elif payload.target_audience:
            # Use legacy target_audience if user_type_filter not provided
            if payload.target_audience == 'students':
                query = query.filter(User.user_type == 'tenant')
            elif payload.target_audience == 'landlords':
                query = query.filter(User.user_type == 'landlord')
            # 'all' doesn't need additional filtering

        # Apply specific user filter
        if payload.specific_users:
            parsed_user_ids = []
            for uid in payload.specific_users:
                try:
                    parsed_user_ids.append(uuid.UUID(uid))
                except Exception:
                    continue
            if parsed_user_ids:
                query = query.filter(User.user_id.in_(parsed_user_ids))

        # Apply university filter (only for students)
        if payload.university_filter:
            query = query.filter(User.user_type == 'tenant')
            query = query.filter(User.university.isnot(None)).filter(User.university.ilike(payload.university_filter))

        # Apply hostel and booking status filter
        if payload.hostel_filter:
            try:
                parsed_hostel_id = uuid.UUID(payload.hostel_filter)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid hostel_id UUID")
            
            # Only target students with bookings
            query = query.filter(User.user_type == 'tenant')
            
            from models import Booking as BookingModel, Room as RoomModel
            today = date.today()
            
            # Use specified booking status or default to confirmed/active
            status_filter = payload.booking_status_filter or ["confirmed", "active"]
            
            student_ids_subq = (
                db.query(BookingModel.student_id)
                .join(RoomModel, BookingModel.room_id == RoomModel.room_id)
                .filter(RoomModel.hostel_id == parsed_hostel_id)
                .filter(BookingModel.student_id.isnot(None))
                .filter(BookingModel.start_date <= today)
                .filter(BookingModel.end_date >= today)
                .filter(func.lower(BookingModel.status).in_([s.lower() for s in status_filter]))
                .distinct()
                .subquery()
            )
            query = query.filter(User.user_id.in_(select(student_ids_subq.c.student_id)))
        
        rows = query.all()
        
        if not rows:
            logger.warning("No device tokens found for advanced targeting criteria")
            return {"status": "skipped", "message": "No users found matching the targeting criteria"}
        
        # Count recipients by type
        student_count = len([1 for (_, u) in rows if getattr(u, 'user_type', None) == 'tenant'])
        landlord_count = len([1 for (_, u) in rows if getattr(u, 'user_type', None) == 'landlord'])
        admin_count = len([1 for (_, u) in rows if getattr(u, 'user_type', None) == 'admin'])
        
        # Get all user IDs from tokens
        user_ids = [dt.user_id for (dt, _) in rows]
        
        # Prepare FCM data payload with type included
        fcm_data = {}
        if data:
            for key, value in data.items():
                fcm_data[str(key)] = str(value) if value is not None else ""
        fcm_data['type'] = notification_type
        
        fcm_responses = []
        
        logger.info(f"Advanced broadcasting notification to {len(rows)} users")
        
        # Send FCM push notifications directly (no database storage)
        for (dt, u) in rows:
            try:
                resp = await send_fcm_push(dt.token, title, body, fcm_data)
                fcm_responses.append({
                    "user_id": str(dt.user_id),
                    "user_type": getattr(u, 'user_type', 'unknown'),
                    "first_name": getattr(u, 'first_name', None),
                    "last_name": getattr(u, 'last_name', None),
                    "full_name": (f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}").strip() or None,
                    "university": getattr(u, 'university', None),
                    "result": resp
                })
            except Exception as e:
                logger.error(f"Error sending FCM to token {dt.token}: {str(e)}")
                fcm_responses.append({
                    "user_id": str(dt.user_id),
                    "user_type": getattr(u, 'user_type', 'unknown'),
                    "first_name": getattr(u, 'first_name', None),
                    "last_name": getattr(u, 'last_name', None),
                    "full_name": (f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}").strip() or None,
                    "university": getattr(u, 'university', None),
                    "error": str(e)
                })
        
        # Calculate success counts by user type
        student_success = len([r for r in fcm_responses if r.get("user_type") == 'tenant' and r.get("result", {}).get("success")])
        landlord_success = len([r for r in fcm_responses if r.get("user_type") == 'landlord' and r.get("result", {}).get("success")])
        admin_success = len([r for r in fcm_responses if r.get("user_type") == 'admin' and r.get("result", {}).get("success")])
        student_failed = len([r for r in fcm_responses if r.get("user_type") == 'tenant' and not r.get("result", {}).get("success")])
        landlord_failed = len([r for r in fcm_responses if r.get("user_type") == 'landlord' and not r.get("result", {}).get("success")])
        admin_failed = len([r for r in fcm_responses if r.get("user_type") == 'admin' and not r.get("result", {}).get("success")])

        fcm_sent = len([r for r in fcm_responses if r.get("result", {}).get("success")])
        fcm_failed_count = len([r for r in fcm_responses if not r.get("result", {}).get("success")])

        # Create broadcast log for audit
        try:
            broadcast_log = BroadcastLog(
                broadcast_type='advanced',
                title=title,
                body=body,
                notification_type=notification_type,
                target_audience=payload.target_audience,
                targeting_criteria={
                    "user_type_filter": payload.user_type_filter,
                    "specific_users_count": len(payload.specific_users) if payload.specific_users else 0,
                    "specific_users": payload.specific_users,
                    "university_filter": payload.university_filter,
                    "hostel_filter": payload.hostel_filter,
                    "booking_status_filter": payload.booking_status_filter
                },
                recipients_summary={
                    "students": {"total": student_count, "sent": student_success, "failed": student_failed},
                    "landlords": {"total": landlord_count, "sent": landlord_success, "failed": landlord_failed},
                    "admins": {"total": admin_count, "sent": admin_success, "failed": admin_failed}
                },
                fcm_sent=fcm_sent,
                fcm_failed=fcm_failed_count,
                fcm_responses=fcm_responses
            )
            db.add(broadcast_log)
            db.commit()
            logger.info(f"Advanced broadcast log created: {broadcast_log.broadcast_id}")
        except Exception as log_error:
            logger.error(f"Failed to create broadcast log: {str(log_error)}")
            # Don't fail the request if logging fails
            db.rollback()

        return {
            "status": "success",
            "message": f"Advanced broadcast notification sent to {len(rows)} users",
            "targeting": {
                "target_audience": payload.target_audience,
                "user_type_filter": payload.user_type_filter,
                "specific_users_count": len(payload.specific_users) if payload.specific_users else 0,
                "university_filter": payload.university_filter,
                "hostel_filter": payload.hostel_filter,
                "booking_status_filter": payload.booking_status_filter
            },
            "recipients": {
                "total": len(rows),
                "students": {
                    "total": student_count,
                    "sent": student_success,
                    "failed": student_failed
                },
                "landlords": {
                    "total": landlord_count,
                    "sent": landlord_success,
                    "failed": landlord_failed
                },
                "admins": {
                    "total": admin_count,
                    "sent": admin_success,
                    "failed": admin_failed
                }
            },
            "fcm_sent": fcm_sent,
            "fcm_failed": fcm_failed_count,
            "fcm_responses": fcm_responses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in advanced_broadcast_notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Helper Endpoints for Admin Targeting
# ============================================

@router.get('/targeting/universities')
async def get_universities(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get list of all universities from users table.
    Returns unique list of universities for targeting purposes.
    """
    try:
        universities = db.query(User.university).filter(
            User.university.isnot(None),
            User.user_type == 'tenant'  # Only students have universities
        ).distinct().all()
        
        university_list = [uni[0] for uni in universities if uni[0]]
        university_list.sort()
        
        return {
            "universities": university_list,
            "count": len(university_list)
        }
    except Exception as e:
        logger.error(f"Error fetching universities: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch universities")

@router.get('/targeting/hostels')
async def get_hostels(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get list of all hostels with booking statistics.
    Returns hostels with information about active/confirmed bookings.
    """
    try:
        from models import Hostel as HostelModel, Booking as BookingModel, Room as RoomModel
        
        hostels = db.query(HostelModel).filter(HostelModel.is_active == True).all()
        
        hostel_list = []
        today = date.today()
        
        for hostel in hostels:
            # Count bookings by status for this hostel
            booking_stats = db.query(
                BookingModel.status,
                func.count(BookingModel.booking_id).label('count')
            ).join(RoomModel, BookingModel.room_id == RoomModel.room_id)\
             .filter(RoomModel.hostel_id == hostel.hostel_id)\
             .filter(BookingModel.student_id.isnot(None))\
             .filter(BookingModel.start_date <= today)\
             .filter(BookingModel.end_date >= today)\
             .group_by(BookingModel.status).all()
            
            stats_dict = {stat.status.lower(): stat.count for stat in booking_stats}
            
            hostel_list.append({
                "hostel_id": str(hostel.hostel_id),
                "name": hostel.name,
                "university": hostel.university,
                "district": hostel.district,
                "booking_stats": {
                    "confirmed": stats_dict.get('confirmed', 0),
                    "active": stats_dict.get('active', 0),
                    "pending": stats_dict.get('pending', 0),
                    "total": sum(stats_dict.values())
                }
            })
        
        # Sort by name
        hostel_list.sort(key=lambda x: x['name'])
        
        return {
            "hostels": hostel_list,
            "count": len(hostel_list)
        }
    except Exception as e:
        logger.error(f"Error fetching hostels: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch hostels")

@router.get('/targeting/booking-statuses')
async def get_booking_statuses():
    """
    Get list of valid booking statuses for filtering.
    """
    return {
        "booking_statuses": [
            {"value": "pending", "label": "Pending"},
            {"value": "confirmed", "label": "Confirmed"},
            {"value": "active", "label": "Active"},
            {"value": "completed", "label": "Completed"},
            {"value": "cancelled", "label": "Cancelled"}
        ]
    }


# ---- USAGE NOTES ----
# Call /notifications/register-token from your Flutter app on login/register to save a device token.
# Call /notifications/send from booking/payment event in your backend to notify affected users.
# Call /notifications/broadcast from admin dashboard to send system-wide notifications to ALL users.
# 
# Notification Management Endpoints:
# - GET /notifications?user_id={uuid} - Get notifications with optional filters (is_read, type, limit, offset)
# - GET /notifications/{notification_id}?user_id={uuid} - Get a specific notification
# - PUT /notifications/{notification_id}/read?user_id={uuid} - Mark a notification as read
# - PUT /notifications/read-all?user_id={uuid}&type={type} - Mark all notifications as read (optionally filtered by type)
# - DELETE /notifications/{notification_id}?user_id={uuid} - Delete a specific notification
# - DELETE /notifications?user_id={uuid}&is_read={bool}&type={type}&delete_all={bool} - Delete notifications with filters
# - GET /notifications/stats/summary?user_id={uuid} - Get notification statistics
# 
# Admin Notification Endpoints:
# - POST /notifications/broadcast - Send notification to ALL users with FCM tokens

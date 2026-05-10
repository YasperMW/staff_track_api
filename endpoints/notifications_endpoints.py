from datetime import datetime
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.db_models import User, Notification, UserFCMToken
from endpoints.auth_endpoints import get_current_user
from fcm_service import send_push_notification, send_multicast_push_notification, test_fcm_connectivity, send_fcm_push_enhanced

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"], redirect_slashes=False)

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

class AdvancedBroadcastNotification(BaseModel):
    title: str
    body: str
    notification_type: str = "general"
    data: Optional[dict] = None
    
    # Enhanced targeting options
    target_audience: Optional[str] = "all"  # 'all', 'department', 'role'
    specific_users: Optional[List[str]] = None  # Specific user IDs
    department_filter: Optional[str] = None  # Department name filter
    role_filter: Optional[str] = None  # Role name filter
    user_type_filter: Optional[List[str]] = None  # Multiple user types
    status_filter: Optional[str] = None  # User status filter (active, inactive, etc.)

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

@router.get("/test-fcm-connectivity", response_model=dict)
async def test_fcm_connection(
    current_user: User = Depends(get_current_user)
):
    """Test FCM connectivity and return diagnostic information"""
    # Only admins can test FCM connectivity
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can test FCM connectivity"
        )
    
    result = await test_fcm_connectivity()
    return result

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

@router.get("", response_model=List[NotificationResponse])
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

@router.post("", response_model=NotificationResponse)
async def create_notification(
    notification: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new notification"""
    
    # Only admins can create notifications for other users
    if notification.recipient_user_id and current_user.role.name not in ['HR', 'System Admin']:
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
    Enhanced with better FCM logic and audit logging from other_app_notification.py.
    Only admins can send broadcast notifications.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can send broadcast notifications"
        )

    try:
        # Validate notification type
        valid_types = ['app_update', 'maintenance', 'incident', 'general', 'attendance', 'system']
        notification_type = broadcast.notification_type if broadcast.notification_type in valid_types else 'general'

        # Build query based on target audience
        query = db.query(UserFCMToken, User).join(User, UserFCMToken.user_id == User.user_id)
        
        # Apply filters
        query = query.filter(User.deleted_at.is_(None), User.status == 'active')

        if broadcast.target == "department" and broadcast.target_value:
            from models.db_models import Department
            department = db.query(Department).filter(
                Department.name.ilike(f"%{broadcast.target_value}%"),
                Department.deleted_at.is_(None)
            ).first()
            if department:
                query = query.filter(User.department_id == department.department_id)

        elif broadcast.target == "role" and broadcast.target_value:
            from models.db_models import Role
            role = db.query(Role).filter(
                Role.name.ilike(f"%{broadcast.target_value}%"),
                Role.deleted_at.is_(None)
            ).first()
            if role:
                query = query.filter(User.role_id == role.role_id)

        rows = query.all()
        
        if not rows:
            logger.warning(f"No device tokens found for target: {broadcast.target}")
            return {"status": "skipped", "message": f"No users found matching the target criteria: {broadcast.target}"}
        
        # Count recipients by role
        role_counts = {}
        for (_, user) in rows:
            role_name = getattr(user.role, 'name', 'unknown') if user.role else 'unknown'
            role_counts[role_name] = role_counts.get(role_name, 0) + 1
        
        # Prepare FCM data payload with type included
        fcm_data = broadcast.data or {}
        fcm_data['type'] = notification_type
        fcm_data['sent_at'] = datetime.now().isoformat()
        
        fcm_responses = []
        
        logger.info(f"Broadcasting notification to {len(rows)} users (target: {broadcast.target})")
        
        # Send FCM push notifications using enhanced function
        for (token_record, user) in rows:
            try:
                resp = await send_fcm_push_enhanced(
                    token=token_record.fcm_token,
                    title=broadcast.title,
                    body=broadcast.body,
                    data=fcm_data,
                    priority="high",
                    notification_type=notification_type
                )
                fcm_responses.append({
                    "user_id": str(token_record.user_id),
                    "user_name": f"{user.first_name} {user.surname}".strip(),
                    "role": getattr(user.role, 'name', 'unknown') if user.role else 'unknown',
                    "department": getattr(user.department, 'name', 'unknown') if user.department else 'unknown',
                    "result": resp
                })
            except Exception as e:
                logger.error(f"Error sending FCM to token {token_record.fcm_token}: {str(e)}")
                fcm_responses.append({
                    "user_id": str(token_record.user_id),
                    "user_name": f"{user.first_name} {user.surname}".strip(),
                    "role": getattr(user.role, 'name', 'unknown') if user.role else 'unknown',
                    "department": getattr(user.department, 'name', 'unknown') if user.department else 'unknown',
                    "error": str(e)
                })
        
        # Calculate success counts
        fcm_sent = len([r for r in fcm_responses if r.get("result", {}).get("success")])
        fcm_failed_count = len([r for r in fcm_responses if not r.get("result", {}).get("success")])

        # Create broadcast log for audit
        try:
            from models.db_models import BroadcastLog
            broadcast_log = BroadcastLog(
                broadcast_type='simple',
                title=broadcast.title,
                body=broadcast.body,
                notification_type=notification_type,
                target_audience=broadcast.target,
                targeting_criteria={
                    "target": broadcast.target,
                    "target_value": broadcast.target_value
                },
                recipients_summary={
                    "total": len(rows),
                    "by_role": role_counts
                },
                fcm_sent=fcm_sent,
                fcm_failed=fcm_failed_count,
                fcm_responses=fcm_responses,
                created_by=current_user.user_id
            )
            db.add(broadcast_log)
            db.commit()
            logger.info(f"Broadcast log created: {broadcast_log.broadcast_id}")
        except Exception as log_error:
            logger.error(f"Failed to create broadcast log: {str(log_error)}")
            db.rollback()

        # Create in-app notifications for each user
        for (token_record, user) in rows:
            new_notification = Notification(
                user_id=token_record.user_id,
                title=broadcast.title,
                message=broadcast.body,
                type=notification_type,
                is_read=False,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(new_notification)

        db.commit()

        return {
            "status": "success",
            "message": f"Broadcast notification sent to {len(rows)} users",
            "target": broadcast.target,
            "target_value": broadcast.target_value,
            "recipients": {
                "total": len(rows),
                "by_role": role_counts
            },
            "fcm_sent": fcm_sent,
            "fcm_failed": fcm_failed_count,
            "in_app_created": len(rows),
            "fcm_responses": fcm_responses[:10]  # Return first 10 responses for brevity
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in broadcast notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/broadcast/types", response_model=dict)
async def get_notification_types():
    """Get available notification types for broadcast"""
    return {
        "notification_types": [
            {"value": "app_update", "label": "App Update", "description": "Notify users about app updates"},
            {"value": "maintenance", "label": "Maintenance Alert", "description": "Scheduled or emergency maintenance notifications"},
            {"value": "incident", "label": "Incident Report", "description": "Important incident or safety alerts"},
            {"value": "general", "label": "General Announcement", "description": "General information for all users"},
            {"value": "attendance", "label": "Attendance", "description": "Attendance-related notifications"},
            {"value": "system", "label": "System", "description": "System notifications and alerts"}
        ],
        "targets": [
            {"value": "all", "label": "All Users"},
            {"value": "department", "label": "Specific Department"},
            {"value": "role", "label": "Specific Role"}
        ]
    }

@router.get("/targeting/departments", response_model=dict)
async def get_departments_for_targeting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of all departments for targeting purposes.
    Only admins can access this endpoint.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access targeting information"
        )
    
    try:
        from models.db_models import Department
        
        departments = db.query(Department).filter(
            Department.deleted_at.is_(None)
        ).all()
        
        department_list = []
        for dept in departments:
            # Count active users in this department
            user_count = db.query(User).filter(
                User.department_id == dept.department_id,
                User.deleted_at.is_(None),
                User.status == 'active'
            ).count()
            
            department_list.append({
                "department_id": str(dept.department_id),
                "name": dept.name,
                "active_users": user_count
            })
        
        # Sort by name
        department_list.sort(key=lambda x: x['name'])
        
        return {
            "departments": department_list,
            "count": len(department_list)
        }
    except Exception as e:
        logger.error(f"Error fetching departments: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch departments")

@router.get("/targeting/roles", response_model=dict)
async def get_roles_for_targeting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of all roles for targeting purposes.
    Only admins can access this endpoint.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access targeting information"
        )
    
    try:
        from models.db_models import Role
        
        roles = db.query(Role).filter(
            Role.deleted_at.is_(None)
        ).all()
        
        role_list = []
        for role in roles:
            # Count active users with this role
            user_count = db.query(User).filter(
                User.role_id == role.role_id,
                User.deleted_at.is_(None),
                User.status == 'active'
            ).count()
            
            role_list.append({
                "role_id": str(role.role_id),
                "name": role.name,
                "active_users": user_count
            })
        
        # Sort by name
        role_list.sort(key=lambda x: x['name'])
        
        return {
            "roles": role_list,
            "count": len(role_list)
        }
    except Exception as e:
        logger.error(f"Error fetching roles: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch roles")

@router.get("/targeting/user-stats", response_model=dict)
async def get_user_statistics_for_targeting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user statistics for targeting purposes.
    Only admins can access this endpoint.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access targeting information"
        )
    
    try:
        # Get overall user statistics
        total_users = db.query(User).filter(User.deleted_at.is_(None)).count()
        active_users = db.query(User).filter(
            User.deleted_at.is_(None),
            User.status == 'active'
        ).count()
        inactive_users = db.query(User).filter(
            User.deleted_at.is_(None),
            User.status != 'active'
        ).count()
        
        # Get users by role
        role_stats = []
        from models.db_models import Role
        roles = db.query(Role).filter(Role.deleted_at.is_(None)).all()
        
        for role in roles:
            count = db.query(User).filter(
                User.role_id == role.role_id,
                User.deleted_at.is_(None),
                User.status == 'active'
            ).count()
            role_stats.append({
                "role_name": role.name,
                "active_users": count
            })
        
        # Get users by department
        dept_stats = []
        from models.db_models import Department
        departments = db.query(Department).filter(Department.deleted_at.is_(None)).all()
        
        for dept in departments:
            count = db.query(User).filter(
                User.department_id == dept.department_id,
                User.deleted_at.is_(None),
                User.status == 'active'
            ).count()
            dept_stats.append({
                "department_name": dept.name,
                "active_users": count
            })
        
        # Get FCM token statistics
        users_with_tokens = db.query(UserFCMToken.user_id).distinct().count()
        
        return {
            "overall": {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": inactive_users,
                "users_with_fcm_tokens": users_with_tokens
            },
            "by_role": role_stats,
            "by_department": dept_stats
        }
    except Exception as e:
        logger.error(f"Error fetching user statistics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch user statistics")

@router.post("/broadcast-advanced", response_model=dict)
async def send_advanced_broadcast_notification(
    broadcast: AdvancedBroadcastNotification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send an advanced broadcast notification with enhanced targeting options.
    Based on the logic from other_app_notification.py.
    Only admins can send broadcast notifications.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can send broadcast notifications"
        )

    try:
        if not broadcast.title or not broadcast.body:
            raise HTTPException(status_code=422, detail="title and body are required")

        # Validate notification type
        valid_types = ['app_update', 'maintenance', 'incident', 'general', 'attendance', 'system']
        notification_type = broadcast.notification_type if broadcast.notification_type in valid_types else 'general'

        # Build query based on targeting options
        query = db.query(UserFCMToken, User).join(User, UserFCMToken.user_id == User.user_id)
        
        # Apply filters
        if broadcast.specific_users:
            # Parse user IDs
            parsed_user_ids = []
            for uid in broadcast.specific_users:
                try:
                    parsed_user_ids.append(uuid.UUID(uid))
                except Exception:
                    continue
            if parsed_user_ids:
                query = query.filter(User.user_id.in_(parsed_user_ids))

        if broadcast.department_filter:
            from models.db_models import Department
            department = db.query(Department).filter(
                Department.name.ilike(f"%{broadcast.department_filter}%"),
                Department.deleted_at.is_(None)
            ).first()
            if department:
                query = query.filter(User.department_id == department.department_id)

        if broadcast.role_filter:
            from models.db_models import Role
            role = db.query(Role).filter(
                Role.name.ilike(f"%{broadcast.role_filter}%"),
                Role.deleted_at.is_(None)
            ).first()
            if role:
                query = query.filter(User.role_id == role.role_id)

        if broadcast.status_filter:
            query = query.filter(User.status == broadcast.status_filter)

        # Filter out deleted users
        query = query.filter(User.deleted_at.is_(None))

        rows = query.all()
        
        if not rows:
            logger.warning("No device tokens found for advanced targeting criteria")
            return {"status": "skipped", "message": "No users found matching the targeting criteria"}
        
        # Count recipients by role
        role_counts = {}
        for (_, user) in rows:
            role_name = getattr(user.role, 'name', 'unknown') if user.role else 'unknown'
            role_counts[role_name] = role_counts.get(role_name, 0) + 1
        
        # Prepare FCM data payload with type included
        fcm_data = broadcast.data or {}
        fcm_data['type'] = notification_type
        fcm_data['broadcast_id'] = str(uuid.uuid4())  # Temporary ID for tracking
        
        fcm_responses = []
        
        logger.info(f"Advanced broadcasting notification to {len(rows)} users")
        
        # Send FCM push notifications using enhanced function
        for (token_record, user) in rows:
            try:
                resp = await send_fcm_push_enhanced(
                    token=token_record.fcm_token,
                    title=broadcast.title,
                    body=broadcast.body,
                    data=fcm_data,
                    priority="high",
                    notification_type=notification_type
                )
                fcm_responses.append({
                    "user_id": str(token_record.user_id),
                    "user_name": f"{user.first_name} {user.surname}".strip(),
                    "role": getattr(user.role, 'name', 'unknown') if user.role else 'unknown',
                    "department": getattr(user.department, 'name', 'unknown') if user.department else 'unknown',
                    "result": resp
                })
            except Exception as e:
                logger.error(f"Error sending FCM to token {token_record.fcm_token}: {str(e)}")
                fcm_responses.append({
                    "user_id": str(token_record.user_id),
                    "user_name": f"{user.first_name} {user.surname}".strip(),
                    "role": getattr(user.role, 'name', 'unknown') if user.role else 'unknown',
                    "department": getattr(user.department, 'name', 'unknown') if user.department else 'unknown',
                    "error": str(e)
                })
        
        # Calculate success counts
        fcm_sent = len([r for r in fcm_responses if r.get("result", {}).get("success")])
        fcm_failed_count = len([r for r in fcm_responses if not r.get("result", {}).get("success")])

        # Create broadcast log for audit
        try:
            from models.db_models import BroadcastLog
            broadcast_log = BroadcastLog(
                broadcast_type='advanced',
                title=broadcast.title,
                body=broadcast.body,
                notification_type=notification_type,
                target_audience=broadcast.target_audience,
                targeting_criteria={
                    "specific_users_count": len(broadcast.specific_users) if broadcast.specific_users else 0,
                    "specific_users": broadcast.specific_users,
                    "department_filter": broadcast.department_filter,
                    "role_filter": broadcast.role_filter,
                    "user_type_filter": broadcast.user_type_filter,
                    "status_filter": broadcast.status_filter
                },
                recipients_summary={
                    "total": len(rows),
                    "by_role": role_counts
                },
                fcm_sent=fcm_sent,
                fcm_failed=fcm_failed_count,
                fcm_responses=fcm_responses,
                created_by=current_user.user_id
            )
            db.add(broadcast_log)
            db.commit()
            logger.info(f"Advanced broadcast log created: {broadcast_log.broadcast_id}")
        except Exception as log_error:
            logger.error(f"Failed to create broadcast log: {str(log_error)}")
            db.rollback()

        # Create in-app notifications for each user
        for (token_record, user) in rows:
            new_notification = Notification(
                user_id=token_record.user_id,
                title=broadcast.title,
                message=broadcast.body,
                type=notification_type,
                is_read=False,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(new_notification)

        db.commit()

        return {
            "status": "success",
            "message": f"Advanced broadcast notification sent to {len(rows)} users",
            "targeting": {
                "target_audience": broadcast.target_audience,
                "specific_users_count": len(broadcast.specific_users) if broadcast.specific_users else 0,
                "department_filter": broadcast.department_filter,
                "role_filter": broadcast.role_filter,
                "status_filter": broadcast.status_filter
            },
            "recipients": {
                "total": len(rows),
                "by_role": role_counts
            },
            "fcm_sent": fcm_sent,
            "fcm_failed": fcm_failed_count,
            "in_app_created": len(rows),
            "fcm_responses": fcm_responses[:10]  # Return first 10 responses for brevity
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in advanced broadcast notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/broadcast-logs", response_model=dict)
async def get_broadcast_logs(
    page: int = 1,
    per_page: int = 20,
    broadcast_type: Optional[str] = None,
    notification_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get paginated list of broadcast logs for audit purposes.
    Only admins can access broadcast logs.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access broadcast logs"
        )
    
    try:
        from models.db_models import BroadcastLog
        
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
                    "body": log.body[:200] + "..." if len(log.body) > 200 else log.body,
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
    except Exception as e:
        logger.error(f"Error fetching broadcast logs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch broadcast logs")

@router.get("/broadcast-logs/{broadcast_id}", response_model=dict)
async def get_broadcast_log_detail(
    broadcast_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed broadcast log by ID including full FCM responses.
    Only admins can access broadcast logs.
    """
    # Check admin permissions
    admin_roles = ['HR', 'System Admin', 'Principal Hospital Administrator', 'System Administrator']
    if current_user.role.name not in admin_roles:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access broadcast logs"
        )
    
    try:
        from models.db_models import BroadcastLog
        
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

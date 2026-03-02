from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.db_models import User, Announcement, Department, Role, AnnouncementDepartment, Notification
from endpoints.auth_endpoints import get_current_user

router = APIRouter(tags=["announcements"])

class AnnouncementResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    targetAudience: str
    isActive: bool
    createdAt: str
    authorName: str

class AnnouncementCreate(BaseModel):
    title: str
    message: str
    type: str
    target_departments: Optional[List[str]] = None  # List of department names
    target_role: Optional[str] = None
    is_active: Optional[bool] = True
    expires_at: Optional[str] = None
    attachment_url: Optional[str] = None
    send_notifications: Optional[bool] = True  # Whether to send notifications

@router.get("/", response_model=List[AnnouncementResponse])
async def get_announcements(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    activeOnly: Optional[bool] = None,
    department: Optional[str] = None,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get announcements with optional filters"""
    
    query = db.query(Announcement).filter(Announcement.deleted_at.is_(None))
    
    # Apply filters
    if activeOnly:
        query = query.filter(Announcement.is_active == True)
    
    # Apply order_by before limit/offset
    query = query.order_by(Announcement.created_at.desc())
    
    # Apply pagination
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    
    announcements = query.all()
    
    return [
        AnnouncementResponse(
            id=str(announcement.announcement_id),
            title=announcement.title,
            message=announcement.message,
            type=announcement.type,
            targetAudience=announcement.target_audience,
            isActive=announcement.is_active,
            createdAt=announcement.created_at.isoformat(),
            authorName=f"{announcement.creator.first_name} {announcement.creator.surname}"
        )
        for announcement in announcements
    ]

@router.post("/", response_model=AnnouncementResponse)
async def create_announcement(
    announcement: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new announcement and send notifications to target departments"""
    
    # Parse expires_at if provided
    expires_at = None
    if announcement.expires_at:
        expires_at = datetime.fromisoformat(announcement.expires_at.replace('Z', '+00:00'))
    
    # Determine target audience based on departments and role
    target_audience = "All Staff"
    if announcement.target_departments and len(announcement.target_departments) > 0:
        if len(announcement.target_departments) == 1:
            target_audience = announcement.target_departments[0]
        else:
            target_audience = ", ".join(announcement.target_departments)
    elif announcement.target_role:
        target_audience = announcement.target_role
    
    new_announcement = Announcement(
        title=announcement.title,
        message=announcement.message,
        type=announcement.type,
        target_audience=target_audience,
        is_active=announcement.is_active or True,
        expires_at=expires_at,
        attachment_url=announcement.attachment_url,
        created_by=current_user.user_id,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)
    
    # Add department relationships if specified
    if announcement.target_departments and len(announcement.target_departments) > 0:
        for department_name in announcement.target_departments:
            department = db.query(Department).filter(
                Department.name == department_name,
                Department.deleted_at.is_(None)
            ).first()
            
            if department:
                announcement_dept = AnnouncementDepartment(
                    announcement_id=new_announcement.announcement_id,
                    department_id=department.department_id
                )
                db.add(announcement_dept)
        db.commit()
    
    # Send notifications to target departments if requested
    if announcement.send_notifications and announcement.target_departments and len(announcement.target_departments) > 0:
        await _send_announcement_notifications(
            db, 
            new_announcement, 
            announcement.target_departments, 
            announcement.target_role
        )
    
    return AnnouncementResponse(
        id=str(new_announcement.announcement_id),
        title=new_announcement.title,
        message=new_announcement.message,
        type=new_announcement.type,
        targetAudience=new_announcement.target_audience,
        isActive=new_announcement.is_active,
        createdAt=new_announcement.created_at.isoformat(),
        authorName=f"{current_user.first_name} {current_user.surname}"
    )

async def _send_announcement_notifications(
    db: Session, 
    announcement: Announcement, 
    target_departments: List[str], 
    target_role: Optional[str]
):
    """Send notifications to users in target departments"""
    
    try:
        # Get all users in the target departments
        users_to_notify = db.query(User).join(
            Department, 
            User.department_id == Department.department_id
        ).filter(
            Department.name.in_(target_departments),
            User.deleted_at.is_(None),
            Department.deleted_at.is_(None)
        )
        
        # Filter by role if specified
        if target_role:
            users_to_notify = users_to_notify.join(Role).filter(Role.name == target_role)
        
        users = users_to_notify.all()
        
        # Create notifications for each user
        notifications_to_create = []
        for user in users:
            notification = Notification(
                user_id=user.user_id,
                title=f"📢 {announcement.type.title()}: {announcement.title}",
                message=announcement.message,
                type="announcement",
                is_read=False,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            notifications_to_create.append(notification)
        
        # Bulk insert notifications
        if notifications_to_create:
            db.bulk_save_objects(notifications_to_create)
            db.commit()
            
    except Exception as e:
        # Log error but don't fail the announcement creation
        print(f"Failed to send notifications: {e}")

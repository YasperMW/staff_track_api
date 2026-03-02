from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.db_models import User, Announcement, Department, Role, AnnouncementDepartment, Notification, Holiday
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
    """Get announcements with optional filters, including holidays as announcements"""
    ann_query = db.query(Announcement).filter(Announcement.deleted_at.is_(None))
    if activeOnly:
        ann_query = ann_query.filter(Announcement.is_active == True)
    ann_query = ann_query.order_by(Announcement.created_at.desc())
    announcements = ann_query.all()

    ann_responses: List[AnnouncementResponse] = [
        AnnouncementResponse(
            id=str(a.announcement_id),
            title=a.title,
            message=a.message,
            type=a.type,
            targetAudience=a.target_audience,
            isActive=a.is_active,
            createdAt=a.created_at.isoformat(),
            authorName=f"{a.creator.first_name} {a.creator.surname}" if a.creator else "System"
        )
        for a in announcements
    ]

    hol_query = db.query(Holiday).filter(Holiday.deleted_at.is_(None))
    holidays = hol_query.all()

    holiday_responses: List[AnnouncementResponse] = []
    for h in holidays:
        author = "System"
        if h.category == "institutional" and h.creator:
            author = f"{h.creator.first_name} {h.creator.surname}"
        elif h.category == "public":
            author = "Public Holidays Service"
        msg_parts = [f"📅 Observed on {h.date.strftime('%B %d, %Y')}"]
        if h.description:
            msg_parts.append(f"{h.description}")
        holiday_message = "\n" + " • ".join(msg_parts)
        created_at = h.created_at or datetime.combine(h.date, datetime.min.time())
        holiday_responses.append(
            AnnouncementResponse(
                id=str(h.holiday_id),
                title=h.name,
                message=holiday_message,
                type="holiday",
                targetAudience="All Staff",
                isActive=True,
                createdAt=created_at.isoformat(),
                authorName=author,
            )
        )

    combined = ann_responses + holiday_responses
    combined.sort(key=lambda x: x.createdAt, reverse=True)

    if offset:
        combined = combined[offset:]
    if limit:
        combined = combined[:limit]

    return combined

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

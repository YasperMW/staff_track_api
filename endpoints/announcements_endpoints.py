from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.db_models import User, Announcement, Department, Role, AnnouncementDepartment, Notification, Holiday, UserFCMToken
from endpoints.auth_endpoints import get_current_user
from fcm_service import send_push_notification
from mail_service import email_service

router = APIRouter(tags=["announcements"], redirect_slashes=False)

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
    
    # Filter by target department if specified or use current user's department
    filter_department = department
    if not filter_department and current_user.department_id:
        user_dept = db.query(Department).filter(
            Department.department_id == current_user.department_id,
            Department.deleted_at.is_(None)
        ).first()
        if user_dept:
            filter_department = user_dept.name
    
    # Get announcements that either have no target departments (All Staff) 
    # or match the filter department
    if filter_department:
        from sqlalchemy import or_
        
        target_dept = db.query(Department).filter(
            Department.name == filter_department,
            Department.deleted_at.is_(None)
        ).first()
        
        if target_dept:
            targeted_ann_ids = [
                ad.announcement_id for ad in 
                db.query(AnnouncementDepartment).filter(
                    AnnouncementDepartment.department_id == target_dept.department_id
                ).all()
            ]
            
            all_targeted_ids = set(
                ad.announcement_id for ad in 
                db.query(AnnouncementDepartment.announcement_id).distinct().all()
            )
            
            if targeted_ann_ids or all_targeted_ids:
                untargeted_filter = []
                if all_targeted_ids:
                    untargeted_filter.append(Announcement.announcement_id.notin_(all_targeted_ids))
                elif targeted_ann_ids:
                    untargeted_filter.append(Announcement.announcement_id.notin_(targeted_ann_ids))
                
                ann_query = ann_query.filter(
                    or_(
                        Announcement.announcement_id.in_(targeted_ann_ids) if targeted_ann_ids else False,
                        *untargeted_filter
                    )
                )
    
    if role:
        role_targeted_ann_ids = [
            ad.announcement_id for ad in 
            db.query(AnnouncementDepartment).join(Department).filter(
                Department.name == role
            ).all()
        ]
        if role_targeted_ann_ids:
            ann_query = ann_query.filter(
                Announcement.announcement_id.in_(role_targeted_ann_ids)
            )
    
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
            announcement.target_role,
            f"{current_user.first_name} {current_user.surname}"
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
    target_role: Optional[str],
    creator_name: str = None
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
            
            # Send FCM push notifications and emails to users
            for user in users:
                # Send push notifications
                if user.fcm_tokens:
                    for token_record in user.fcm_tokens:
                        await send_push_notification(
                            token=token_record.fcm_token,
                            title=f"📢 {announcement.type.title()}: {announcement.title}",
                            body=announcement.message,
                            data={
                                "announcement_id": str(announcement.announcement_id),
                                "type": "announcement"
                            }
                        )
                
                # Send email notifications for urgent and policy announcements
                if (announcement.type.lower() in ["urgent", "policy"] and 
                    user.email and creator_name):
                    try:
                        await email_service.send_announcement_email(
                            email=user.email,
                            recipient_name=f"{user.first_name} {user.surname}",
                            announcement_title=announcement.title,
                            announcement_message=announcement.message,
                            announcement_type=announcement.type,
                            target_audience=announcement.target_audience,
                            author_name=creator_name
                        )
                    except Exception as e:
                        print(f"Failed to send announcement email to {user.email}: {e}")
            
    except Exception as e:
        # Log error but don't fail the announcement creation
        print(f"Failed to send notifications: {e}")


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    type: Optional[str] = None
    target_departments: Optional[List[str]] = None
    target_role: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[str] = None
    attachment_url: Optional[str] = None


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: str,
    announcement: AnnouncementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing announcement"""
    
    # Find the announcement
    db_announcement = db.query(Announcement).filter(
        Announcement.announcement_id == announcement_id,
        Announcement.deleted_at.is_(None)
    ).first()
    
    if not db_announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    # Update fields if provided
    if announcement.title is not None:
        db_announcement.title = announcement.title
    if announcement.message is not None:
        db_announcement.message = announcement.message
    if announcement.type is not None:
        db_announcement.type = announcement.type
    if announcement.is_active is not None:
        db_announcement.is_active = announcement.is_active
    if announcement.attachment_url is not None:
        db_announcement.attachment_url = announcement.attachment_url
    
    # Parse expires_at if provided
    if announcement.expires_at is not None:
        if announcement.expires_at:
            db_announcement.expires_at = datetime.fromisoformat(
                announcement.expires_at.replace('Z', '+00:00')
            )
        else:
            db_announcement.expires_at = None
    
    # Update target audience based on departments and role
    if announcement.target_departments is not None:
        # Remove old department relationships
        db.query(AnnouncementDepartment).filter(
            AnnouncementDepartment.announcement_id == announcement_id
        ).delete()
        
        # Add new department relationships
        if len(announcement.target_departments) > 0:
            if len(announcement.target_departments) == 1:
                db_announcement.target_audience = announcement.target_departments[0]
            else:
                db_announcement.target_audience = ", ".join(announcement.target_departments)
            
            for dept_name in announcement.target_departments:
                department = db.query(Department).filter(
                    Department.name == dept_name,
                    Department.deleted_at.is_(None)
                ).first()
                
                if department:
                    ann_dept = AnnouncementDepartment(
                        announcement_id=announcement_id,
                        department_id=department.department_id
                    )
                    db.add(ann_dept)
        else:
            db_announcement.target_audience = "All Staff"
    
    db_announcement.updated_at = datetime.now()
    db.commit()
    db.refresh(db_announcement)
    
    return AnnouncementResponse(
        id=str(db_announcement.announcement_id),
        title=db_announcement.title,
        message=db_announcement.message,
        type=db_announcement.type,
        targetAudience=db_announcement.target_audience,
        isActive=db_announcement.is_active,
        createdAt=db_announcement.created_at.isoformat(),
        authorName=f"{db_announcement.creator.first_name} {db_announcement.creator.surname}" if db_announcement.creator else "System"
    )

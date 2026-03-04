from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, NotificationPreference
from notification_service import NotificationService
from datetime import datetime

router = APIRouter(prefix="/notification-preferences", tags=["notification-preferences"])

class NotificationPreferenceResponse(BaseModel):
    category: str
    email_enabled: bool
    push_enabled: bool
    in_app_enabled: bool

class UpdateNotificationPreferenceRequest(BaseModel):
    category: str
    email_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None

class BulkUpdatePreferencesRequest(BaseModel):
    preferences: List[UpdateNotificationPreferenceRequest]

@router.get("/", response_model=List[NotificationPreferenceResponse])
async def get_my_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's notification preferences"""
    preferences = NotificationService.get_user_preferences(db, str(current_user.user_id))
    
    return [
        NotificationPreferenceResponse(
            category=category,
            email_enabled=prefs['email_enabled'],
            push_enabled=prefs['push_enabled'],
            in_app_enabled=prefs['in_app_enabled']
        )
        for category, prefs in preferences.items()
    ]

@router.get("/stats")
async def get_my_notification_stats(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's notification statistics"""
    stats = NotificationService.get_notification_stats(db, str(current_user.user_id), hours)
    return stats

@router.put("/{category}")
async def update_notification_preference(
    category: str,
    request: UpdateNotificationPreferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a specific notification preference"""
    # Validate category
    valid_categories = list(NotificationService.NOTIFICATION_CATEGORIES.keys())
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )
    
    NotificationService.update_user_preference(
        db,
        str(current_user.user_id),
        category,
        request.email_enabled,
        request.push_enabled,
        request.in_app_enabled
    )
    
    return {"success": True, "message": f"Notification preference for {category} updated successfully"}

@router.put("/bulk")
async def bulk_update_notification_preferences(
    request: BulkUpdatePreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update multiple notification preferences at once"""
    valid_categories = list(NotificationService.NOTIFICATION_CATEGORIES.keys())
    
    for pref_request in request.preferences:
        if pref_request.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category: {pref_request.category}. Must be one of: {', '.join(valid_categories)}"
            )
        
        NotificationService.update_user_preference(
            db,
            str(current_user.user_id),
            pref_request.category,
            pref_request.email_enabled,
            pref_request.push_enabled,
            pref_request.in_app_enabled
        )
    
    return {"success": True, "message": "Notification preferences updated successfully"}

@router.post("/reset")
async def reset_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reset all notification preferences to default values"""
    valid_categories = list(NotificationService.NOTIFICATION_CATEGORIES.keys())
    
    for category in valid_categories:
        NotificationService.update_user_preference(
            db,
            str(current_user.user_id),
            category,
            email_enabled=True,
            push_enabled=True,
            in_app_enabled=True
        )
    
    return {"success": True, "message": "All notification preferences reset to defaults"}

@router.get("/categories")
async def get_notification_categories():
    """Get available notification categories"""
    return {
        "categories": [
            {
                "name": category,
                "description": category.replace('_', ' ').title(),
                "types": types,
                "rate_limit": NotificationService.RATE_LIMITS.get(category, 10),
                "dedup_window": NotificationService.DEDUPLICATION_WINDOWS.get(category, 10)
            }
            for category, types in NotificationService.NOTIFICATION_CATEGORIES.items()
        ]
    }

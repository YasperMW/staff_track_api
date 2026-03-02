from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import requests
import json

from database import get_db
from models.db_models import User, Holiday
from endpoints.auth_endpoints import get_current_user

router = APIRouter(tags=["holidays"])

class HolidayResponse(BaseModel):
    id: str
    name: str
    date: str
    description: Optional[str]
    type: Optional[str]
    category: str
    source: Optional[str]
    isRecurring: bool

class HolidayCreate(BaseModel):
    name: str
    date: str
    description: Optional[str] = None
    type: Optional[str] = None
    category: str = "institutional"  # 'public' or 'institutional'
    isRecurring: bool = False

@router.get("/", response_model=List[HolidayResponse])
async def get_holidays(
    year: Optional[int] = None,
    category: Optional[str] = None,  # Filter by 'public' or 'institutional'
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get holidays for a specific year, optionally filtered by category"""
    
    target_year = year or datetime.now().year
    
    # Build query
    query = db.query(Holiday).filter(
        Holiday.deleted_at.is_(None),
        func.extract('year', Holiday.date) == target_year
    )
    
    # Add category filter if specified
    if category:
        query = query.filter(Holiday.category == category)
    
    holidays = query.order_by(Holiday.date.asc()).all()
    
    return [
        HolidayResponse(
            id=str(holiday.holiday_id),
            name=holiday.name,
            date=holiday.date.isoformat(),
            description=holiday.description,
            type=holiday.type,
            category=holiday.category,
            source=holiday.source,
            isRecurring=holiday.is_recurring
        )
        for holiday in holidays
    ]

@router.get("/upcoming", response_model=List[HolidayResponse])
async def get_upcoming_holidays(
    months: int = 3,
    category: Optional[str] = None,  # Filter by 'public' or 'institutional'
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get upcoming holidays within specified months, optionally filtered by category"""
    
    current_date = datetime.now().date()
    target_date = datetime(current_date.year + (current_date.month + months - 1) // 12, 
                          ((current_date.month + months - 1) % 12) + 1, 1).date()
    
    # Build query
    query = db.query(Holiday).filter(
        Holiday.deleted_at.is_(None),
        Holiday.date > current_date,
        Holiday.date <= target_date
    )
    
    # Add category filter if specified
    if category:
        query = query.filter(Holiday.category == category)
    
    holidays = query.order_by(Holiday.date.asc()).all()
    
    return [
        HolidayResponse(
            id=str(holiday.holiday_id),
            name=holiday.name,
            date=holiday.date.isoformat(),
            description=holiday.description,
            type=holiday.type,
            category=holiday.category,
            source=holiday.source,
            isRecurring=holiday.is_recurring
        )
        for holiday in holidays
    ]

@router.post("/", response_model=HolidayResponse)
async def create_holiday(
    holiday: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new holiday (institutional or public)"""
    
    holiday_date = datetime.strptime(holiday.date, "%Y-%m-%d").date()
    
    new_holiday = Holiday(
        name=holiday.name,
        date=holiday_date,
        description=holiday.description,
        type=holiday.type or ("Institutional Holiday" if holiday.category == "institutional" else "Public Holiday"),
        category=holiday.category,
        source="manual" if holiday.category == "institutional" else None,
        country_code="MW" if holiday.category == "public" else None,
        is_recurring=holiday.isRecurring,
        created_by=current_user.user_id if holiday.category == "institutional" else None,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    db.add(new_holiday)
    db.commit()
    db.refresh(new_holiday)
    
    return HolidayResponse(
        id=str(new_holiday.holiday_id),
        name=new_holiday.name,
        date=new_holiday.date.isoformat(),
        description=new_holiday.description,
        type=new_holiday.type,
        category=new_holiday.category,
        source=new_holiday.source,
        isRecurring=new_holiday.is_recurring
    )

@router.post("/fetch-public", response_model=List[HolidayResponse])
async def fetch_public_holidays(
    year: int,
    country_code: str = "MW",  # Default to Malawi
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch public holidays from external API and store them"""
    
    try:
        # Using a free public holidays API (you may need to sign up for an API key)
        # For demonstration, we'll use a mock implementation
        # In production, you'd use a real API like calendarific.com or similar
        
        # Mock data for Malawi public holidays (replace with real API call)
        mock_holidays = [
            {"name": "New Year's Day", "date": f"{year}-01-01", "type": "National Holiday"},
            {"name": "John Chilembwe Day", "date": f"{year}-01-15", "type": "National Holiday"},
            {"name": "Martyrs' Day", "date": f"{year}-03-03", "type": "National Holiday"},
            {"name": "Good Friday", "date": f"{year}-04-07", "type": "Religious Holiday"},
            {"name": "Easter Monday", "date": f"{year}-04-10", "type": "Religious Holiday"},
            {"name": "Labour Day", "date": f"{year}-05-01", "type": "National Holiday"},
            {"name": "Kamuzu Day", "date": f"{year}-05-14", "type": "National Holiday"},
            {"name": "Independence Day", "date": f"{year}-07-06", "type": "National Holiday"},
            {"name": "Mother's Day", "date": f"{year}-10-15", "type": "National Holiday"},
            {"name": "Christmas Day", "date": f"{year}-12-25", "type": "Religious Holiday"},
            {"name": "Boxing Day", "date": f"{year}-12-26", "type": "National Holiday"},
        ]
        
        stored_holidays = []
        
        for holiday_data in mock_holidays:
            # Check if holiday already exists
            existing = db.query(Holiday).filter(
                Holiday.deleted_at.is_(None),
                Holiday.name == holiday_data["name"],
                Holiday.date == datetime.strptime(holiday_data["date"], "%Y-%m-%d").date(),
                Holiday.category == "public"
            ).first()
            
            if not existing:
                new_holiday = Holiday(
                    name=holiday_data["name"],
                    date=datetime.strptime(holiday_data["date"], "%Y-%m-%d").date(),
                    description=f"Public holiday in {country_code}",
                    type=holiday_data["type"],
                    category="public",
                    source="government_api",
                    country_code=country_code,
                    is_recurring=True,  # Most public holidays are recurring
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                db.add(new_holiday)
                db.commit()
                db.refresh(new_holiday)
                
                stored_holidays.append(HolidayResponse(
                    id=str(new_holiday.holiday_id),
                    name=new_holiday.name,
                    date=new_holiday.date.isoformat(),
                    description=new_holiday.description,
                    type=new_holiday.type,
                    category=new_holiday.category,
                    source=new_holiday.source,
                    isRecurring=new_holiday.is_recurring
                ))
        
        return stored_holidays
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch public holidays: {str(e)}")

@router.delete("/{holiday_id}")
async def delete_holiday(
    holiday_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a holiday (only institutional holidays can be deleted by users)"""
    
    holiday = db.query(Holiday).filter(
        Holiday.holiday_id == holiday_id,
        Holiday.deleted_at.is_(None)
    ).first()
    
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    if holiday.category == "public" and holiday.source == "government_api":
        raise HTTPException(status_code=403, detail="Cannot delete public holidays fetched from government API")
    
    # Soft delete
    holiday.deleted_at = datetime.now()
    holiday.deleted_by = current_user.user_id
    holiday.updated_at = datetime.now()
    
    db.commit()
    
    return {"message": "Holiday deleted successfully"}

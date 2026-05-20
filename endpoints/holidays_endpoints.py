from datetime import datetime, date
from timezone_config import get_current_time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import requests
import json
import os

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
    
    target_year = year or get_current_time().year
    
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
    
    current_date = get_current_time().date()
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
        created_at=get_current_time(),
        updated_at=get_current_time()
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
    country_code: str = "MW",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    provider = os.getenv("HOLIDAYS_API_PROVIDER", "calendarific").lower()
    api_key = os.getenv("HOLIDAYS_API_KEY", "")
    try:
        stored_holidays: List[HolidayResponse] = []
        if provider == "calendarific" and api_key:
            url = "https://calendarific.com/api/v2/holidays"
            params = {"api_key": api_key, "country": country_code, "year": year}
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"Calendarific error {resp.status_code}")
            data = resp.json()
            items = data.get("response", {}).get("holidays", []) or []
            for h in items:
                name = h.get("name") or ""
                date_str = (h.get("date", {}).get("iso") or "")[:10]
                htypes = h.get("type") or []
                htype = (htypes[0] if isinstance(htypes, list) and htypes else "National").lower()
                type_map = {"national": "national", "religious": "religious"}
                type_val = type_map.get(htype, "custom")
                if not name or not date_str:
                    continue
                existing = db.query(Holiday).filter(
                    Holiday.deleted_at.is_(None),
                    Holiday.name == name,
                    Holiday.date == datetime.strptime(date_str, "%Y-%m-%d").date(),
                    Holiday.category == "public"
                ).first()
                if not existing:
                    new_holiday = Holiday(
                        name=name,
                        date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                        description=f"Public holiday in {country_code}",
                        type=type_val,
                        category="public",
                        source="calendarific",
                        country_code=country_code,
                        is_recurring=True,
                        created_at=get_current_time(),
                        updated_at=get_current_time()
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
        else:
            url = f"https://date.nager.at/api/v3/publicholidays/{year}/{country_code}"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"Nager error {resp.status_code}")
            items = resp.json()
            for h in items:
                name = h.get("localName") or h.get("name") or ""
                date_str = h.get("date") or ""
                types = h.get("types") or []
                t0 = types[0] if isinstance(types, list) and types else "Public"
                t0 = t0.lower()
                type_map = {"public": "national", "religion": "religious"}
                type_val = type_map.get(t0, "custom")
                if not name or not date_str:
                    continue
                existing = db.query(Holiday).filter(
                    Holiday.deleted_at.is_(None),
                    Holiday.name == name,
                    Holiday.date == datetime.strptime(date_str, "%Y-%m-%d").date(),
                    Holiday.category == "public"
                ).first()
                if not existing:
                    new_holiday = Holiday(
                        name=name,
                        date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                        description=f"Public holiday in {country_code}",
                        type=type_val,
                        category="public",
                        source="nager",
                        country_code=country_code,
                        is_recurring=True,
                        created_at=get_current_time(),
                        updated_at=get_current_time()
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
    holiday.deleted_at = get_current_time()
    holiday.deleted_by = current_user.user_id
    holiday.updated_at = get_current_time()
    
    db.commit()
    
    return {"message": "Holiday deleted successfully"}

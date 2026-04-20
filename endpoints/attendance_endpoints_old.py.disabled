from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, date
from datetime import datetime, time
from typing import Optional
import pytz

from models.db_models import Attendance, User
from database import get_db
from auth_endpoints import get_current_user

router = APIRouter(prefix="/attendance", tags=["attendance"])

@router.post("/check-in")
async def check_in(
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check in the current user"""
    
    # Check if user already checked in today
    today = datetime.now().date()
    existing_attendance = db.query(Attendance).filter(
        and_(
            Attendance.user_id == current_user.user_id,
            Attendance.date == today
        )
    ).first()
    
    if existing_attendance and existing_attendance.check_in_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already checked in today"
        )
    
    # Create or update attendance record
    if existing_attendance:
        existing_attendance.check_in_time = datetime.now().time()
        existing_attendance.check_in_location = location
        existing_attendance.check_in_latitude = latitude
        existing_attendance.check_in_longitude = longitude
        existing_attendance.updated_at = datetime.now()
        attendance = existing_attendance
    else:
        attendance = Attendance(
            user_id=current_user.user_id,
            date=today,
            check_in_time=datetime.now().time(),
            check_in_location=location,
            check_in_latitude=latitude,
            check_in_longitude=longitude,
            status="present",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(attendance)
    
    db.commit()
    db.refresh(attendance)
    
    return {
        "message": "Check-in successful",
        "attendance_id": str(attendance.attendance_id),
        "check_in_time": attendance.check_in_time.strftime("%H:%M:%S"),
        "location": location
    }

@router.post("/check-out")
async def check_out(
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check out the current user"""
    
    # Find today's attendance record
    today = datetime.now().date()
    attendance = db.query(Attendance).filter(
        and_(
            Attendance.user_id == current_user.user_id,
            Attendance.date == today
        )
    ).first()
    
    if not attendance or not attendance.check_in_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No check-in record found for today"
        )
    
    if attendance.check_out_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already checked out today"
        )
    
    # Update attendance record
    attendance.check_out_time = datetime.now().time()
    attendance.check_out_location = location
    attendance.check_out_latitude = latitude
    attendance.check_out_longitude = longitude
    attendance.updated_at = datetime.now()
    
    # Calculate work hours
    check_in_datetime = datetime.combine(today, attendance.check_in_time)
    check_out_datetime = datetime.combine(today, attendance.check_out_time)
    work_hours = (check_out_datetime - check_in_datetime).total_seconds() / 3600.0
    
    attendance.work_hours = round(work_hours, 2)
    
    # Calculate overtime (assuming 8 hours is standard work day)
    if work_hours > 8:
        attendance.overtime_hours = round(work_hours - 8, 2)
    
    db.commit()
    db.refresh(attendance)
    
    return {
        "message": "Check-out successful",
        "attendance_id": str(attendance.attendance_id),
        "check_out_time": attendance.check_out_time.strftime("%H:%M:%S"),
        "work_hours": attendance.work_hours,
        "overtime_hours": attendance.overtime_hours,
        "location": location
    }

@router.get("/today")
async def get_today_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get today's attendance record for the current user"""
    
    today = datetime.now().date()
    attendance = db.query(Attendance).filter(
        and_(
            Attendance.user_id == current_user.user_id,
            Attendance.date == today
        )
    ).first()
    
    if not attendance:
        return {"message": "No attendance record for today"}
    
    return {
        "attendance_id": str(attendance.attendance_id),
        "date": attendance.date.strftime("%Y-%m-%d"),
        "check_in_time": attendance.check_in_time.strftime("%H:%M:%S") if attendance.check_in_time else None,
        "check_out_time": attendance.check_out_time.strftime("%H:%M:%S") if attendance.check_out_time else None,
        "check_in_location": attendance.check_in_location,
        "check_out_location": attendance.check_out_location,
        "work_hours": float(attendance.work_hours) if attendance.work_hours else None,
        "overtime_hours": float(attendance.overtime_hours) if attendance.overtime_hours else None,
        "status": attendance.status
    }

@router.get("/history")
async def get_attendance_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get attendance history for the current user"""
    
    query = db.query(Attendance).filter(Attendance.user_id == current_user.user_id)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(Attendance.date >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Attendance.date <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    attendances = query.order_by(Attendance.date.desc()).limit(limit).all()
    
    return [
        {
            "attendance_id": str(att.attendance_id),
            "date": att.date.strftime("%Y-%m-%d"),
            "check_in_time": att.check_in_time.strftime("%H:%M:%S") if att.check_in_time else None,
            "check_out_time": att.check_out_time.strftime("%H:%M:%S") if att.check_out_time else None,
            "check_in_location": att.check_in_location,
            "check_out_location": att.check_out_location,
            "work_hours": float(att.work_hours) if att.work_hours else None,
            "overtime_hours": float(att.overtime_hours) if att.overtime_hours else None,
            "status": att.status
        }
        for att in attendances
    ]

@router.get("/summary")
async def get_attendance_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get attendance summary for the current user"""
    
    query = db.query(Attendance).filter(Attendance.user_id == current_user.user_id)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(Attendance.date >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Attendance.date <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    # Get summary statistics
    total_days = query.count()
    present_days = query.filter(Attendance.status == "present").count()
    late_days = query.filter(Attendance.status == "late").count()
    
    total_work_hours = db.query(func.coalesce(func.sum(Attendance.work_hours), 0)).filter(
        and_(
            Attendance.user_id == current_user.user_id,
            Attendance.work_hours.isnot(None)
        )
    ).scalar()
    
    total_overtime = db.query(func.coalesce(func.sum(Attendance.overtime_hours), 0)).filter(
        and_(
            Attendance.user_id == current_user.user_id,
            Attendance.overtime_hours.isnot(None)
        )
    ).scalar()
    
    return {
        "total_days": total_days,
        "present_days": present_days,
        "late_days": late_days,
        "total_work_hours": float(total_work_hours),
        "total_overtime_hours": float(total_overtime),
        "average_work_hours": float(total_work_hours) / present_days if present_days > 0 else 0
    }

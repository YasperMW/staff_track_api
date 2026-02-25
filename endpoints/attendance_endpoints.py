from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from datetime import datetime, date, time, timedelta
from typing import Optional
import pytz

from models.db_models import AttendanceLog, User
from database import get_db
from endpoints.auth_endpoints import get_current_user

router = APIRouter(prefix="/attendance", tags=["attendance"])

@router.post("/check-in")
async def check_in(
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    accuracy: Optional[float] = None,
    device_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check in the current user"""
    
    # Check if user already checked in today (not checked out)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    existing_attendance = db.query(AttendanceLog).filter(
        and_(
            AttendanceLog.user_id == current_user.user_id,
            AttendanceLog.check_in_time >= today_start,
            AttendanceLog.check_in_time <= today_end,
            AttendanceLog.check_out_time.is_(None)
        )
    ).first()
    
    if existing_attendance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already checked in today. Please check out first."
        )
    
    # Create location string if lat/lng provided
    location_str = None
    if latitude is not None and longitude is not None:
        location_str = f"POINT({longitude} {latitude})"
    elif location:
        location_str = location
    
    # Create attendance log
    attendance = AttendanceLog(
        user_id=current_user.user_id,
        check_in_time=datetime.now(),
        location=location_str,
        accuracy=accuracy,
        device_id=device_id,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    
    return {
        "message": "Check-in successful",
        "attendance_log_id": str(attendance.attendance_log_id),
        "check_in_time": attendance.check_in_time.strftime("%H:%M:%S"),
        "location": location_str
    }

@router.post("/check-out")
async def check_out(
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    accuracy: Optional[float] = None,
    device_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check out the current user"""
    
    # Find today's active attendance record (checked in but not out)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    attendance = db.query(AttendanceLog).filter(
        and_(
            AttendanceLog.user_id == current_user.user_id,
            AttendanceLog.check_in_time >= today_start,
            AttendanceLog.check_in_time <= today_end,
            AttendanceLog.check_out_time.is_(None)
        )
    ).first()
    
    if not attendance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active check-in record found for today"
        )
    
    # Update location if provided
    if latitude is not None and longitude is not None:
        attendance.location = f"POINT({longitude} {latitude})"
    elif location:
        attendance.location = location
    
    if accuracy is not None:
        attendance.accuracy = accuracy
    
    if device_id is not None:
        attendance.device_id = device_id
    
    # Update check out time
    attendance.check_out_time = datetime.now()
    attendance.updated_at = datetime.now()
    
    db.commit()
    db.refresh(attendance)
    
    # Calculate work hours
    work_hours = (attendance.check_out_time - attendance.check_in_time).total_seconds() / 3600.0
    
    return {
        "message": "Check-out successful",
        "attendance_log_id": str(attendance.attendance_log_id),
        "check_out_time": attendance.check_out_time.strftime("%H:%M:%S"),
        "work_hours": round(work_hours, 2),
        "location": attendance.location
    }

@router.get("/today")
async def get_today_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get today's attendance record for the current user"""
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    attendance = db.query(AttendanceLog).filter(
        and_(
            AttendanceLog.user_id == current_user.user_id,
            AttendanceLog.check_in_time >= today_start,
            AttendanceLog.check_in_time <= today_end
        )
    ).order_by(desc(AttendanceLog.check_in_time)).first()
    
    if not attendance:
        return {"message": "No attendance record for today"}
    
    # Calculate work hours if checked out
    work_hours = None
    if attendance.check_out_time:
        work_hours = (attendance.check_out_time - attendance.check_in_time).total_seconds() / 3600.0
    
    return {
        "attendance_log_id": str(attendance.attendance_log_id),
        "date": attendance.check_in_time.strftime("%Y-%m-%d"),
        "check_in_time": attendance.check_in_time.strftime("%H:%M:%S"),
        "check_out_time": attendance.check_out_time.strftime("%H:%M:%S") if attendance.check_out_time else None,
        "location": attendance.location,
        "work_hours": round(work_hours, 2) if work_hours else None,
        "device_id": attendance.device_id,
        "accuracy": float(attendance.accuracy) if attendance.accuracy else None
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
    
    query = db.query(AttendanceLog).filter(AttendanceLog.user_id == current_user.user_id)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(AttendanceLog.check_in_time <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    attendances = query.order_by(desc(AttendanceLog.check_in_time)).limit(limit).all()
    
    result = []
    for att in attendances:
        work_hours = None
        if att.check_out_time:
            work_hours = (att.check_out_time - att.check_in_time).total_seconds() / 3600.0
        
        result.append({
            "attendance_log_id": str(att.attendance_log_id),
            "date": att.check_in_time.strftime("%Y-%m-%d"),
            "check_in_time": att.check_in_time.strftime("%H:%M:%S"),
            "check_out_time": att.check_out_time.strftime("%H:%M:%S") if att.check_out_time else None,
            "location": att.location,
            "work_hours": round(work_hours, 2) if work_hours else None,
            "device_id": att.device_id,
            "accuracy": float(att.accuracy) if att.accuracy else None
        })
    
    return result

@router.get("/summary")
async def get_attendance_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(AttendanceLog).filter(AttendanceLog.user_id == current_user.user_id)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(AttendanceLog.check_in_time <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    attendances = query.all()
    
    if not attendances:
        return {
            "total_days": 0,
            "present_days": 0,
            "late_days": 0,
            "total_work_hours": 0,
            "total_overtime_hours": 0,
            "average_work_hours": 0
        }
    
    total_days = len(attendances)
    present_days = len([a for a in attendances if a.check_out_time is not None])
    
    late_days = 0
    total_work_seconds = 0
    total_overtime_seconds = 0
    
    for att in attendances:
        if att.check_in_time:
            check_in_hour = att.check_in_time.hour
            if check_in_hour >= 9:
                late_days += 1
        
        if att.check_out_time:
            work_seconds = (att.check_out_time - att.check_in_time).total_seconds()
            total_work_seconds += work_seconds
            
            work_hours = work_seconds / 3600.0
            if work_hours > 8:
                total_overtime_seconds += (work_hours - 8) * 3600.0
    
    total_work_hours = total_work_seconds / 3600.0
    total_overtime_hours = total_overtime_seconds / 3600.0
    
    return {
        "total_days": total_days,
        "present_days": present_days,
        "late_days": late_days,
        "total_work_hours": round(total_work_hours, 2),
        "total_overtime_hours": round(total_overtime_hours, 2),
        "average_work_hours": round(total_work_hours / present_days, 2) if present_days > 0 else 0
    }


@router.get("/team-today-summary")
async def get_team_today_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return {
            "total_staff": 0,
            "present": 0,
            "absent": 0,
            "late": 0
        }
    
    staff_ids = [u.user_id for u in staff]
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id.in_(staff_ids),
            AttendanceLog.check_in_time >= today_start,
            AttendanceLog.check_in_time <= today_end,
        )
        .order_by(AttendanceLog.user_id, AttendanceLog.check_in_time)
        .all()
    )
    
    earliest_by_user = {}
    
    for log in logs:
        uid = log.user_id
        if uid not in earliest_by_user or log.check_in_time < earliest_by_user[uid]:
            earliest_by_user[uid] = log.check_in_time
    
    present_count = len(earliest_by_user)
    late_count = 0
    
    for dt in earliest_by_user.values():
        if dt.hour >= 9:
            late_count += 1
    
    total_staff = len(staff)
    absent_count = total_staff - present_count
    
    return {
        "total_staff": total_staff,
        "present": present_count,
        "absent": absent_count,
        "late": late_count
    }


@router.get("/team-today-list")
async def get_team_today_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return []
    
    staff_ids = [u.user_id for u in staff]
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id.in_(staff_ids),
            AttendanceLog.check_in_time >= today_start,
            AttendanceLog.check_in_time <= today_end,
        )
        .order_by(AttendanceLog.user_id, AttendanceLog.check_in_time)
        .all()
    )
    
    earliest_log_by_user = {}
    latest_checkout_by_user = {}
    
    for log in logs:
        uid = log.user_id
        if log.check_in_time:
            if uid not in earliest_log_by_user or log.check_in_time < earliest_log_by_user[uid].check_in_time:
                earliest_log_by_user[uid] = log
        if log.check_out_time:
            existing = latest_checkout_by_user.get(uid)
            if existing is None or log.check_out_time > existing:
                latest_checkout_by_user[uid] = log.check_out_time
    
    result = []
    
    for user in staff:
        log = earliest_log_by_user.get(user.user_id)
        check_in_time_str = None
        check_out_time_str = None
        status = "Absent"
        
        if log and log.check_in_time:
            check_in_time = log.check_in_time
            hour = check_in_time.hour
            status = "Late" if hour >= 9 else "Present"
            check_in_time_str = check_in_time.strftime("%H:%M:%S")
        
        checkout_dt = latest_checkout_by_user.get(user.user_id)
        if checkout_dt:
            check_out_time_str = checkout_dt.strftime("%H:%M:%S")
        
        full_name = f"{user.first_name or ''} {user.surname or ''}".strip()
        role_name = user.role.name if getattr(user, "role", None) else ""
        
        result.append(
            {
                "user_id": str(user.user_id),
                "name": full_name,
                "role": role_name,
                "status": status,
                "check_in_time": check_in_time_str,
                "check_out_time": check_out_time_str,
            }
        )
    
    return result


@router.get("/department-overview")
async def get_department_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return {
            "avg_attendance": 0,
            "total_overtime_hours": 0
        }
    
    staff_ids = [u.user_id for u in staff]
    
    first_day = date.today().replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1, day=1)
    
    start_dt = datetime.combine(first_day, time.min)
    end_dt = datetime.combine(next_month, time.min)
    
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id.in_(staff_ids),
            AttendanceLog.check_in_time >= start_dt,
            AttendanceLog.check_in_time < end_dt,
        )
        .all()
    )
    
    if not logs:
        return {
            "avg_attendance": 0,
            "total_overtime_hours": 0
        }
    
    present_by_user = set()
    total_overtime_seconds = 0.0
    
    for log in logs:
        if log.check_in_time:
            key = (log.user_id, log.check_in_time.date())
            present_by_user.add(key)
        
        if log.check_in_time and log.check_out_time:
            work_seconds = (log.check_out_time - log.check_in_time).total_seconds()
            work_hours = work_seconds / 3600.0
            if work_hours > 8:
                total_overtime_seconds += (work_hours - 8) * 3600.0
    
    total_days_in_month = (end_dt.date() - first_day).days
    if total_days_in_month <= 0:
        avg_attendance = 0.0
    else:
        total_possible = len(staff) * total_days_in_month
        attendance_ratio = len(present_by_user) / total_possible if total_possible > 0 else 0.0
        avg_attendance = round(attendance_ratio * 100, 1)
    
    total_overtime_hours = round(total_overtime_seconds / 3600.0, 2)
    
    return {
        "avg_attendance": avg_attendance,
        "total_overtime_hours": total_overtime_hours
    }


@router.get("/department-weekly")
async def get_department_weekly_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return {"points": []}
    
    staff_ids = [u.user_id for u in staff]
    
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=7)
    
    start_dt = datetime.combine(start_of_week, time.min)
    end_dt = datetime.combine(end_of_week, time.min)
    
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id.in_(staff_ids),
            AttendanceLog.check_in_time >= start_dt,
            AttendanceLog.check_in_time < end_dt,
        )
        .all()
    )
    
    present_by_day = {}
    
    for log in logs:
        if log.check_in_time:
            d = log.check_in_time.date()
            if d < start_of_week or d >= end_of_week:
                continue
            key = (log.user_id, d)
            present_by_day[key] = True
    
    total_staff = len(staff)
    total_possible_per_day = total_staff if total_staff > 0 else 1
    
    points = []
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        label = day.strftime("%a")[:3]
        present_count = len([1 for (uid, d) in present_by_day.keys() if d == day])
        ratio = present_count / total_possible_per_day
        percentage = round(ratio * 100, 1)
        points.append(
            {
                "label": label,
                "percentage": percentage,
            }
        )
    
    return {"points": points}


@router.get("/department-top-performers")
async def get_department_top_performers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return {"performers": []}
    
    staff_ids = [u.user_id for u in staff]
    
    first_day = date.today().replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1, day=1)
    
    start_dt = datetime.combine(first_day, time.min)
    end_dt = datetime.combine(next_month, time.min)
    
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id.in_(staff_ids),
            AttendanceLog.check_in_time >= start_dt,
            AttendanceLog.check_in_time < end_dt,
        )
        .all()
    )
    
    if not logs:
        return {"performers": []}
    
    present_days_by_user = {}
    
    for log in logs:
        if log.check_in_time:
            key = (log.user_id, log.check_in_time.date())
            present_days_by_user[key] = True
    
    days_in_month = (end_dt.date() - first_day).days
    if days_in_month <= 0:
        return {"performers": []}
    
    user_present_counts = {}
    for (uid, d) in present_days_by_user.keys():
        user_present_counts[uid] = user_present_counts.get(uid, 0) + 1
    
    performers = []
    for user in staff:
        present_days = user_present_counts.get(user.user_id, 0)
        attendance_ratio = present_days / days_in_month
        attendance_percentage = round(attendance_ratio * 100, 1)
        full_name = f"{user.first_name or ''} {user.surname or ''}".strip()
        role_name = user.designation.name if getattr(user, "designation", None) else ""
        performers.append(
            {
                "user_id": str(user.user_id),
                "name": full_name,
                "role": role_name,
                "attendance_percentage": attendance_percentage,
            }
        )
    
    performers.sort(key=lambda p: p["attendance_percentage"], reverse=True)
    
    top_performers = performers[:5]
    
    return {"performers": top_performers}

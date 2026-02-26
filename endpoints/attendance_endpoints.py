from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc, text
from datetime import datetime, date, time, timedelta
from typing import Optional
import pytz
from geoalchemy2 import functions as geofuncs
from geoalchemy2.elements import WKTElement

from models.db_models import AttendanceLog, User
from database import get_db
from endpoints.auth_endpoints import get_current_user

router = APIRouter(prefix="/attendance", tags=["attendance"])

# Define timezone for consistent datetime handling
TIMEZONE = pytz.timezone('Africa/Blantyre')  # Adjust to your timezone

def get_current_time():
    """Get current timezone-aware datetime"""
    return datetime.now(TIMEZONE)

@router.post("/check-in")
async def check_in(
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    accuracy: Optional[float] = None,
    device_id: Optional[str] = None,
    shift_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check in current user"""
    
    # Debug logging
    print(f"DEBUG: Check-in request received:")
    print(f"  location: {location}")
    print(f"  latitude: {latitude}")
    print(f"  longitude: {longitude}")
    print(f"  accuracy: {accuracy}")
    print(f"  device_id: {device_id}")
    print(f"  shift_type: {shift_type}")
    print(f"  user_id: {current_user.user_id}")
    
    # Check if user already checked in today (not checked out)
    current_time = get_current_time()
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
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
    
    # Determine shift if not provided
    if not shift_type:
        check_in_hour = current_time.hour
        check_in_minute = current_time.minute
        
        # Day shift: 07:30 to 16:30
        if (check_in_hour >= 7 and check_in_hour < 16) or (check_in_hour == 7 and check_in_minute >= 30):
            shift_type = "Day Shift"
        # Night shift: 16:30 to 07:30 (next day)
        else:
            shift_type = "Night Shift"
    
    # Create location as PostGIS geography if lat/lng provided
    location_geo = None
    location_str = None
    if latitude is not None and longitude is not None:
        # Create PostGIS geography point from coordinates
        location_geo = WKTElement(f'POINT({longitude} {latitude})', srid=4326)
        location_str = f"POINT({longitude} {latitude})"
        print(f"DEBUG: Created location_geo from coordinates: {location_geo}")
        print(f"DEBUG: Created location_str: {location_str}")
    elif location:
        # Try to parse location string as coordinates
        try:
            if location.startswith("POINT("):
                # Extract coordinates from POINT format
                coords = location.replace("POINT(", "").replace(")", "").split()
                if len(coords) == 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    location_geo = WKTElement(f'POINT({lon} {lat})', srid=4326)
                    location_str = location
                    print(f"DEBUG: Parsed location string to coordinates: {location_geo}")
        except Exception as e:
            print(f"DEBUG: Failed to parse location string: {e}")
            location_str = location
    
    print(f"DEBUG: Final location_geo: {location_geo}")
    print(f"DEBUG: Final location_str: {location_str}")
    
    # Create attendance log
    attendance = AttendanceLog(
        user_id=current_user.user_id,
        check_in_time=current_time,  # Use timezone-aware datetime
        location=location_geo,  # Use PostGIS geography object
        accuracy=accuracy,
        device_id=device_id,
        shift_type=shift_type,
        created_at=current_time,  # Use timezone-aware datetime
        updated_at=current_time   # Use timezone-aware datetime
    )
    
    print(f"DEBUG: About to save attendance record:")
    print(f"  attendance.location: {attendance.location}")
    print(f"  attendance.accuracy: {attendance.accuracy}")
    print(f"  attendance.device_id: {attendance.device_id}")
    
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    
    print(f"DEBUG: After database commit:")
    print(f"  saved attendance.location: {attendance.location}")
    print(f"  saved attendance.accuracy: {attendance.accuracy}")
    print(f"  saved attendance.device_id: {attendance.device_id}")
    
    return {
        "message": "Check-in successful",
        "attendance_log_id": str(attendance.attendance_log_id),
        "check_in_time": attendance.check_in_time.strftime("%H:%M:%S"),
        "shift_type": attendance.shift_type,
        "location": location_str  # Return string representation
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
    
    # Debug logging
    print(f"DEBUG: Check-out request received:")
    print(f"  location: {location}")
    print(f"  latitude: {latitude}")
    print(f"  longitude: {longitude}")
    print(f"  accuracy: {accuracy}")
    print(f"  device_id: {device_id}")
    print(f"  user_id: {current_user.user_id}")
    
    # Find today's active attendance record (checked in but not out)
    current_time = get_current_time()
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
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
        attendance.location = WKTElement(f'POINT({longitude} {latitude})', srid=4326)
    elif location:
        try:
            if location.startswith("POINT("):
                # Extract coordinates from POINT format
                coords = location.replace("POINT(", "").replace(")", "").split()
                if len(coords) == 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    attendance.location = WKTElement(f'POINT({lon} {lat})', srid=4326)
        except:
            pass  # Keep existing location if parsing fails
    
    if accuracy is not None:
        attendance.accuracy = accuracy
    
    if device_id is not None:
        attendance.device_id = device_id
    
    # Update check out time
    attendance.check_out_time = current_time  # Use timezone-aware datetime
    attendance.updated_at = current_time   # Use timezone-aware datetime
    
    # Determine final shift type based on check-in and check-out times
    check_in_hour = attendance.check_in_time.hour
    check_out_hour = attendance.check_out_time.hour
    
    # Day shift: 07:30 to 16:30
    if (check_in_hour >= 7 and check_in_hour < 16) or (check_in_hour == 7 and attendance.check_in_time.minute >= 30):
        initial_shift = "Day Shift"
    else:
        initial_shift = "Night Shift"
    
    # Check if worked across shift boundary (extended shift)
    if (check_out_hour >= 16 and initial_shift == "Day Shift") or (check_out_hour < 7 and initial_shift == "Night Shift"):
        attendance.shift_type = f"{initial_shift} → Extended"
    else:
        attendance.shift_type = initial_shift
    
    # Calculate and store work hours
    work_hours = (attendance.check_out_time - attendance.check_in_time).total_seconds() / 3600.0
    attendance.work_hours = work_hours
    
    db.commit()
    db.refresh(attendance)
    
    # Convert PostGIS geography to string for API response
    location_str = None
    if attendance.location:
        # Use ST_AsText to convert geography to WKT string
        location_result = db.execute(
            text("SELECT ST_AsText(location) as location_str FROM attendance_logs WHERE attendance_log_id = :id"),
            {"id": attendance.attendance_log_id}
        ).first()
        if location_result:
            location_str = location_result[0]
    
    return {
        "message": "Check-out successful",
        "attendance_log_id": str(attendance.attendance_log_id),
        "check_out_time": attendance.check_out_time.strftime("%H:%M:%S"),
        "work_hours": round(work_hours, 2),
        "shift_type": attendance.shift_type,
        "location": location_str
    }

@router.get("/today")
async def get_today_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get today's attendance record for the current user"""
    current_time = get_current_time()
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
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
    
    # Convert PostGIS geography to string for API response
    location_str = None
    if attendance.location:
        # Use ST_AsText to convert geography to WKT string
        location_result = db.execute(
            text("SELECT ST_AsText(location) as location_str FROM attendance_logs WHERE attendance_log_id = :id"),
            {"id": attendance.attendance_log_id}
        ).first()
        if location_result:
            location_str = location_result[0]
    
    return {
        "attendance_log_id": str(attendance.attendance_log_id),
        "date": attendance.check_in_time.strftime("%Y-%m-%d"),
        "check_in_time": attendance.check_in_time.strftime("%H:%M:%S"),
        "check_out_time": attendance.check_out_time.strftime("%H:%M:%S") if attendance.check_out_time else None,
        "location": location_str,
        "work_hours": round(work_hours, 2) if work_hours else None,
        "device_id": attendance.device_id,
        "accuracy": float(attendance.accuracy) if attendance.accuracy else None,
        "shift_type": attendance.shift_type
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
            start_dt = TIMEZONE.localize(datetime.strptime(start_date, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = TIMEZONE.localize(datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999))
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
        
        # Convert PostGIS geography to string for API response
        location_str = None
        if att.location:
            # Use ST_AsText to convert geography to WKT string
            location_result = db.execute(
                text("SELECT ST_AsText(location) as location_str FROM attendance_logs WHERE attendance_log_id = :id"),
                {"id": att.attendance_log_id}
            ).first()
            if location_result:
                location_str = location_result[0]
        
        result.append({
            "attendance_log_id": str(att.attendance_log_id),
            "date": att.check_in_time.strftime("%Y-%m-%d"),
            "check_in_time": att.check_in_time.strftime("%H:%M:%S"),
            "check_out_time": att.check_out_time.strftime("%H:%M:%S") if att.check_out_time else None,
            "location": location_str,
            "work_hours": round(work_hours, 2) if work_hours else None,
            "device_id": att.device_id,
            "accuracy": float(att.accuracy) if att.accuracy else None,
            "shift_type": att.shift_type
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
            start_dt = TIMEZONE.localize(datetime.strptime(start_date, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = TIMEZONE.localize(datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999))
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

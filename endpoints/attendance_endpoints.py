from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, desc
from datetime import datetime, date, time, timedelta
from typing import Optional
from pydantic import BaseModel
import os
import math
from geoalchemy2 import WKTElement
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, AttendanceLog, Notification, Role, AuditLog
from models.auth_models import CheckInRequest, CheckOutRequest
from notification_service import NotificationService
from mail_service import email_service
from timezone_config import get_current_time, to_app_timezone, timezone_aware, get_day_start, get_day_end, get_year_start, format_time, format_time_short, format_date

router = APIRouter(prefix="/attendance", tags=["attendance"])

@router.get("/my-profile-metrics")
async def get_my_profile_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Return year-to-date metrics for the current user:
    - working_days: distinct days with a check-in
    - on_time_rate: percentage of present days with first check-in before 09:00
    - leave_used: total approved leave days in the year (inclusive)
    """
    now = get_current_time()
    year_start = get_year_start(now)
    next_year_start = year_start.replace(year=year_start.year + 1)

    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id == current_user.user_id,
            AttendanceLog.check_in_time >= year_start,
            AttendanceLog.check_in_time < next_year_start,
        )
        .order_by(AttendanceLog.check_in_time.asc())
        .all()
    )

    earliest_by_day = {}
    for log in logs:
        if not log.check_in_time:
            continue
        dt = log.check_in_time
        # Normalize to configured timezone
        dt_local = to_app_timezone(dt)
        d = dt_local.date()
        if d not in earliest_by_day or dt_local < earliest_by_day[d]:
            earliest_by_day[d] = dt_local

    working_days = len(earliest_by_day)
    on_time_count = 0
    for first_dt in earliest_by_day.values():
        if first_dt.hour < 9:
            on_time_count += 1
    on_time_rate = round((on_time_count / working_days) * 100.0, 1) if working_days > 0 else 0.0

    # Calculate approved leave days YTD from requests table
    leave_used_days = 0
    rows = db.execute(
        text(
            """
            SELECT start_date, end_date
            FROM requests
            WHERE user_id = :user_id
              AND status = 'approved'
              AND deleted_at IS NULL
              AND end_date >= :year_start
              AND start_date < :next_year_start
            """
        ),
        {
            "user_id": current_user.user_id,
            "year_start": year_start.date().isoformat(),
            "next_year_start": next_year_start.date().isoformat(),
        },
    ).fetchall()

    for row in rows:
        start_date = row[0]
        end_date = row[1] or row[0]
        # Intersect with year window
        a = max(start_date, year_start.date())
        b = min(end_date, (next_year_start.date() - timedelta(days=1)))
        if b >= a:
            leave_used_days += (b - a).days + 1

    return {
        "working_days": working_days,
        "on_time_rate": on_time_rate,
        "leave_used": leave_used_days,
        "year": year_start.year,
    }
@router.post("/check-in")
async def check_in(
    request: CheckInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check in the current user"""
    current_time = get_current_time()
    """Check in current user"""
    
    # Extract data from request
    location = request.location
    latitude = request.latitude
    longitude = request.longitude
    accuracy = request.accuracy
    device_id = request.device_id
    shift_type = request.shift_type
    
    # Validate location data - location is required
    if not location and not (latitude and longitude):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Location data is required. Either provide location string or latitude and longitude."
        )
    
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
        center_lat = os.getenv("GEOFENCE_CENTER_LAT")
        center_lon = os.getenv("GEOFENCE_CENTER_LON")
        radius_m = os.getenv("GEOFENCE_RADIUS_METERS")
        dist = None
        rad = None
        if center_lat and center_lon and radius_m:
            try:
                clat = float(center_lat)
                clon = float(center_lon)
                rad = float(radius_m)
                r = 6371000.0
                dlat = math.radians(latitude - clat)
                dlon = math.radians(longitude - clon)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(clat))*math.cos(math.radians(latitude))*math.sin(dlon/2)**2
                c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
                dist = r*c
            except Exception as e:
                # If geofence calculation fails, log and continue without blocking
                print(f"Geofence calculation error for check-in: {e}")
                dist = None
                rad = None

        # If we successfully calculated distance and have a radius, enforce geofence
        if dist is not None and rad is not None:
            # Debug logging for geofence calculation
            print(f"GEOFENCE DEBUG (Check-in):")
            print(f"  Center: {center_lat}, {center_lon}")
            print(f"  User Location: {latitude}, {longitude}")
            print(f"  Radius: {rad}m")
            print(f"  Distance: {dist:.1f}m")
            print(f"  Is Violation: {dist > rad}")

            if dist > rad:
                # Geofence violation detected - send notifications
                try:
                    # Find supervisor (Head of Department)
                    supervisor = db.query(User).filter(
                        User.department_id == current_user.department_id,
                        User.is_head_of_department == True,
                        User.deleted_at.is_(None)
                    ).first()
                    
                    if supervisor and supervisor.email:
                        # Send email notifications to employee and supervisor
                        await email_service.send_geofence_violation_email(
                            employee_email=current_user.email,
                            employee_name=f"{current_user.first_name} {current_user.surname}",
                            supervisor_email=supervisor.email,
                            supervisor_name=f"{supervisor.first_name} {supervisor.surname}",
                            location=location_str or f"Lat: {latitude}, Lng: {longitude}",
                            distance_outside=dist - rad,
                            check_in_time=current_time.strftime('%H:%M:%S')
                        )
                        
                        # Send push notifications
                        if hasattr(current_user, 'fcm_token') and current_user.fcm_token:
                            await NotificationService.send_notification(
                                db=db,
                                user_id=str(current_user.user_id),
                                title="⚠️ Geofence Violation",
                                message=f"Your check-in was detected {dist - rad:.0f}m outside work area",
                                notification_type="geofence_violation",
                                data={
                                    "type": "geofence_violation",
                                    "location": location_str or f"Lat: {latitude}, Lng: {longitude}",
                                    "distance_outside": f"{dist - rad:.0f}"
                                },
                                force_send=True
                            )
                        
                        if hasattr(supervisor, 'fcm_token') and supervisor.fcm_token:
                            await NotificationService.send_notification(
                                db=db,
                                user_id=str(supervisor.user_id),
                                title="🚨 Geofence Violation Alert",
                                message=f"{current_user.first_name} {current_user.surname} checked in outside work area",
                                notification_type="geofence_violation",
                                data={
                                    "type": "geofence_violation",
                                    "employee_name": f"{current_user.first_name} {current_user.surname}",
                                    "location": location_str or f"Lat: {latitude}, Lng: {longitude}",
                                    "distance_outside": f"{dist - rad:.0f}"
                                },
                                force_send=True
                            )
                    
                    # Create notification record
                    notification = Notification(
                        user_id=current_user.user_id,
                        title="Geofence Violation Detected",
                        message=f"Check-in location was {dist - rad:.0f}m outside work area",
                        type="security",
                        is_read=False,
                        created_at=current_time,
                        updated_at=current_time
                    )
                    db.add(notification)
                    db.commit()
                    
                except Exception as e:
                    print(f"Failed to send geofence violation notifications: {e}")
                
                print(f"RAISING HTTP EXCEPTION: Check-in blocked due to geofence violation")
                # Propagate HTTPException so FastAPI returns 400 and stops processing
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outside allowed work area")

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
    
    # Create attendance log - store local time directly
    attendance = AttendanceLog(
        user_id=current_user.user_id,
        check_in_time=current_time,
        location=location_geo,  # Use PostGIS geography object
        accuracy=accuracy,
        device_id=device_id,
        shift_type=shift_type,
        created_at=current_time,
        updated_at=current_time
    )
    
    print(f"DEBUG: About to save attendance record:")
    print(f"  attendance.location: {attendance.location}")
    print(f"  attendance.accuracy: {attendance.accuracy}")
    print(f"  attendance.device_id: {attendance.device_id}")
    
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    db.add(AuditLog(actor_id=current_user.user_id, action="check_in", entity="attendance", details={"attendance_log_id": str(attendance.attendance_log_id)}))
    db.commit()
    
    print(f"DEBUG: After database commit:")
    print(f"  saved attendance.location: {attendance.location}")
    print(f"  saved attendance.accuracy: {attendance.accuracy}")
    print(f"  saved attendance.device_id: {attendance.device_id}")
    
    # Send check-in confirmation notification
    print(f" CHECK-IN NOTIFICATION PROCESS STARTING")
    print(f"   User: {current_user.first_name} {current_user.surname} ({current_user.user_id})")
    print(f"   Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Location: {location_str or 'N/A'}")
    print(f"   Shift: {attendance.shift_type or 'Day Shift'}")
    
    try:
        result = await NotificationService.send_notification(
            db=db,
            user_id=str(current_user.user_id),
            title=" Check-in Successful",
            message=f"Checked in at {current_time.strftime('%H:%M')} • {attendance.shift_type or 'Day Shift'}",
            notification_type="attendance",
            data={
                "type": "check_in_confirmation",
                "attendance_log_id": str(attendance.attendance_log_id),
                "check_in_time": current_time.isoformat(),
                "shift_type": attendance.shift_type or "Day Shift"
            },
            force_send=True
        )
        
        if result.get("status") == "success":
            print(f" CHECK-IN NOTIFICATION SENT SUCCESSFULLY")
            print(f"   Result: {result}")
        else:
            print(f" CHECK-IN NOTIFICATION FAILED")
            print(f"   Result: {result}")
        
        # Create in-app notification
        notification = Notification(
            user_id=current_user.user_id,
            title=" Check-in Successful",
            message=f"You successfully checked in at {current_time.strftime('%H:%M')} for {attendance.shift_type or 'Day Shift'}",
            type="attendance",
            is_read=False,
            created_at=current_time,
            updated_at=current_time
        )
        db.add(notification)
        db.commit()
        db.add(AuditLog(actor_id=current_user.user_id, action="check_in", entity="attendance", details={"attendance_log_id": str(attendance.attendance_log_id)}))
        db.commit()
        
        print(f" CHECK-IN NOTIFICATION PROCESS COMPLETED")
    
    except Exception as e:
        print(f"Failed to send check-in notification: {e}")
    
    return {
        "message": "Check-in successful",
        "attendance_log_id": str(attendance.attendance_log_id),
        "check_in_time": format_time(attendance.check_in_time),
        "shift_type": attendance.shift_type,
        "location": location_str  # Return string representation
    }

@router.post("/check-out")
async def check_out(
    request: CheckOutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check out the current user"""
    current_time = get_current_time()
    """Check out the current user"""
    
    # Extract data from request
    location = request.location
    latitude = request.latitude
    longitude = request.longitude
    accuracy = request.accuracy
    device_id = request.device_id
    
    # Validate location data - location is required
    if not location and not (latitude and longitude):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Location data is required. Either provide location string or latitude and longitude."
        )
    
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
    
    # Update location if provided and check geofence
    location_geo = None
    location_str = None
    if latitude is not None and longitude is not None:
        # Check geofence violation
        center_lat = os.getenv("GEOFENCE_CENTER_LAT")
        center_lon = os.getenv("GEOFENCE_CENTER_LON")
        radius_m = os.getenv("GEOFENCE_RADIUS_METERS")
        dist = None
        rad = None
        if center_lat and center_lon and radius_m:
            try:
                clat = float(center_lat)
                clon = float(center_lon)
                rad = float(radius_m)
                r = 6371000.0
                dlat = math.radians(latitude - clat)
                dlon = math.radians(longitude - clon)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(clat))*math.cos(math.radians(latitude))*math.sin(dlon/2)**2
                c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
                dist = r*c
            except Exception as e:
                print(f"Geofence calculation error for check-out: {e}")
                dist = None
                rad = None

        if dist is not None and rad is not None:
            # Debug logging for geofence calculation
            print(f"GEOFENCE DEBUG (Check-out):")
            print(f"  Center: {center_lat}, {center_lon}")
            print(f"  User Location: {latitude}, {longitude}")
            print(f"  Radius: {rad}m")
            print(f"  Distance: {dist:.1f}m")
            print(f"  Is Violation: {dist > rad}")
            
            if dist > rad:
                # Geofence violation detected - send notifications and block
                try:
                    # Find supervisor (Head of Department)
                    supervisor = db.query(User).filter(
                        User.department_id == current_user.department_id,
                        User.is_head_of_department == True,
                        User.deleted_at.is_(None)
                    ).first()
                    
                    if supervisor and supervisor.email:
                        # Send email notifications to employee and supervisor
                        await email_service.send_geofence_violation_email(
                            employee_email=current_user.email,
                            employee_name=f"{current_user.first_name} {current_user.surname}",
                            supervisor_email=supervisor.email,
                            supervisor_name=f"{supervisor.first_name} {supervisor.surname}",
                            location=f"Lat: {latitude}, Lng: {longitude}",
                            distance_outside=dist - rad,
                            check_in_time=current_time.strftime('%H:%M:%S')
                        )
                        
                        # Send push notifications
                        from models.db_models import UserFCMToken
                        fcm_tokens = db.query(UserFCMToken).filter(UserFCMToken.user_id == current_user.user_id).all()
                        if fcm_tokens:
                            for token_record in fcm_tokens:
                                await send_push_notification(
                                    token=token_record.fcm_token,
                                    title="⚠️ Geofence Violation",
                                    body=f"Your check-out was detected {dist - rad:.0f}m outside of work area",
                                    data={
                                        "type": "geofence_violation",
                                        "action": "check_out",
                                        "distance": dist - rad,
                                        "location": f"Lat: {latitude}, Lng: {longitude}"
                                    }
                                )
                        
                        if supervisor:
                            supervisor_fcm_tokens = db.query(UserFCMToken).filter(UserFCMToken.user_id == supervisor.user_id).all()
                            if supervisor_fcm_tokens:
                                for token_record in supervisor_fcm_tokens:
                                    await send_push_notification(
                                        token=token_record.fcm_token,
                                        title="🚨 Geofence Violation Alert",
                                        body=f"{current_user.first_name} {current_user.surname} checked out outside work area",
                                        data={
                                            "type": "team_geofence_violation",
                                            "action": "check_out",
                                            "employee_id": str(current_user.user_id),
                                            "employee_name": f"{current_user.first_name} {current_user.surname}",
                                            "distance": dist - rad
                                        }
                                    )
                    
                    # Create notification record
                    notification = Notification(
                        user_id=current_user.user_id,
                        title="Geofence Violation Detected",
                        message=f"Check-out location was {dist - rad:.0f}m outside work area",
                        type="security",
                        is_read=False,
                        created_at=current_time,
                        updated_at=current_time
                    )
                    db.add(notification)
                    db.commit()
                    
                except Exception as e:
                    print(f"Failed to send geofence violation notifications for check-out: {e}")
                
                # Block check-out for geofence violations (same as check-in)
                print(f"RAISING HTTP EXCEPTION: Check-out blocked due to geofence violation")
                print(f"DEBUG: Check-out blocked due to geofence violation. Distance: {dist:.1f}m, Radius: {rad}m")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outside allowed work area")
        
        # Update location
        attendance.location = WKTElement(f'POINT({longitude} {latitude})', srid=4326)
        location_str = f"POINT({longitude} {latitude})"
    elif location:
        try:
            if location.startswith("POINT("):
                # Extract coordinates from POINT format
                coords = location.replace("POINT(", "").replace(")", "").split()
                if len(coords) == 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    attendance.location = WKTElement(f'POINT({lon} {lat})', srid=4326)
                    location_str = location
        except Exception as e:
            print(f"DEBUG: Failed to parse location string for check-out: {e}")
            location_str = location
    
    if accuracy is not None:
        attendance.accuracy = accuracy
    
    if device_id is not None:
        attendance.device_id = device_id
    
    # Update check out time - store local time directly
    attendance.check_out_time = current_time
    attendance.updated_at = current_time
    
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
    # Ensure both datetimes are naive for subtraction
    check_in_naive = attendance.check_in_time.replace(tzinfo=None) if attendance.check_in_time.tzinfo else attendance.check_in_time
    check_out_naive = attendance.check_out_time.replace(tzinfo=None) if attendance.check_out_time.tzinfo else attendance.check_out_time
    work_hours = (check_out_naive - check_in_naive).total_seconds() / 3600.0
    attendance.work_hours = work_hours
    
    db.commit()
    db.refresh(attendance)
    db.add(AuditLog(actor_id=current_user.user_id, action="check_out", entity="attendance", details={"attendance_log_id": str(attendance.attendance_log_id), "work_hours": float(work_hours)}))
    db.commit()
    
    # Send check-out confirmation notification
    try:
        await NotificationService.send_notification(
            db=db,
            user_id=str(current_user.user_id),
            title="✅ Check-out Successful",
            message=f"Checked out at {format_time_short(attendance.check_out_time)} • {round(work_hours, 1)} hours worked",
            notification_type="attendance",
            data={
                "type": "check_out_confirmation",
                "attendance_log_id": str(attendance.attendance_log_id),
                "check_out_time": attendance.check_out_time.isoformat(),
                "work_hours": f"{round(work_hours, 1)}",
                "shift_type": attendance.shift_type
            },
            force_send=True
        )

        # Create in-app notification
        notification = Notification(
            user_id=current_user.user_id,
            title="✅ Check-out Successful",
            message=f"You successfully checked out at {format_time_short(attendance.check_out_time)}. Total hours worked: {round(work_hours, 1)}",
            type="attendance",
            is_read=False,
            created_at=current_time,
            updated_at=current_time
        )
        db.add(notification)
        db.commit()
        
    except Exception as e:
        print(f"Failed to send check-out notification: {e}")
    
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
        "check_out_time": format_time(attendance.check_out_time),
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
        "date": format_date(attendance.check_in_time),
        "check_in_time": format_time(attendance.check_in_time),
        "check_out_time": format_time(attendance.check_out_time),
        "location": location_str,
        "work_hours": round(work_hours, 2) if work_hours else None,
        "device_id": attendance.device_id,
        "accuracy": float(attendance.accuracy) if attendance.accuracy else None,
        "shift_type": attendance.shift_type
    }

@router.post("/test-notifications")
async def test_attendance_notifications(
    notification_type: str = "check_in_reminder",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test endpoint for attendance notifications"""
    try:
        from attendance_scheduler import attendance_scheduler
        
        if notification_type == "check_in_reminder":
            await attendance_scheduler._send_check_in_reminder(db, current_user)
            return {"message": "Check-in reminder test sent"}
        elif notification_type == "check_out_reminder":
            await attendance_scheduler._send_check_out_reminder(db, current_user)
            return {"message": "Check-out reminder test sent"}
        else:
            return {"error": "Invalid notification type. Use 'check_in_reminder' or 'check_out_reminder'"}
            
    except Exception as e:
        return {"error": f"Failed to send test notification: {e}"}

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
            start_dt = get_day_start(datetime.strptime(start_date, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = get_day_end(datetime.strptime(end_date, "%Y-%m-%d"))
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
            "date": format_date(att.check_in_time),
            "check_in_time": format_time(att.check_in_time),
            "check_out_time": format_time(att.check_out_time),
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
            start_dt = get_day_start(datetime.strptime(start_date, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = get_day_end(datetime.strptime(end_date, "%Y-%m-%d"))
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
    
    today_start = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
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
    
    today_start = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
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
            check_in_time_str = format_time(check_in_time)

        checkout_dt = latest_checkout_by_user.get(user.user_id)
        if checkout_dt:
            check_out_time_str = format_time(checkout_dt)
        
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


@router.get("/team/today/summary")
async def get_team_today_summary_v2(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Team today summary endpoint with forward slashes - returns data in frontend format"""
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return {
            "total_staff": 0,
            "present": 0,
            "absent": 0,
            "late": 0,
            "total_work_hours": 0
        }
    
    staff_ids = [u.user_id for u in staff]
    
    today_start = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
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
    total_work_hours = 0
    
    for log in logs:
        uid = log.user_id
        if uid not in earliest_by_user or log.check_in_time < earliest_by_user[uid]:
            earliest_by_user[uid] = log

        # Calculate work hours for completed shifts
        if log.check_out_time:
            work_hours = (log.check_out_time - log.check_in_time).total_seconds() / 3600.0
            total_work_hours += work_hours

    present_count = len(earliest_by_user)
    late_count = 0

    for log in earliest_by_user.values():
        if log.check_in_time.hour >= 9:
            late_count += 1

    total_staff = len(staff)
    absent_count = total_staff - present_count

    return {
        "total_staff": total_staff,
        "present": present_count,
        "absent": absent_count,
        "late": late_count,
        "total_work_hours": round(total_work_hours, 2)
    }


@router.get("/team/today/list")
async def get_team_today_list_v2(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Team today list endpoint with forward slashes - returns data in frontend format"""
    from models.db_models import Department
    
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    
    if current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    # Join with department to get department name
    staff_query = staff_query.outerjoin(Department, User.department_id == Department.department_id)
    
    staff = staff_query.all()
    
    if not staff:
        return {"staff": []}
    
    staff_ids = [u.user_id for u in staff]
    
    today_start = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
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
    
    staff_list = []
    
    for user in staff:
        log = earliest_log_by_user.get(user.user_id)
        check_in_time_str = None
        check_out_time_str = None
        status = "Absent"
        shift_type = None
        
        if log and log.check_in_time:
            check_in_time = log.check_in_time
            hour = check_in_time.hour
            status = "Late" if hour >= 9 else "Present"
            check_in_time_str = check_in_time.isoformat()
            shift_type = log.shift_type
        
        checkout_dt = latest_checkout_by_user.get(user.user_id)
        if checkout_dt:
            check_out_time_str = checkout_dt.isoformat()
        
        # Get department name from the joined department
        department_name = "Unknown"
        if hasattr(user, 'department') and user.department:
            department_name = user.department.name
        elif hasattr(user, '_Department') and user._Department:
            department_name = user._Department.name
        
        staff_list.append({
            "user_id": str(user.user_id),
            "first_name": user.first_name or "",
            "surname": user.surname or "",
            "employee_number": user.employee_number or "",
            "department": {
                "name": department_name
            },
            "check_in_time": check_in_time_str,
            "check_out_time": check_out_time_str,
            "status": status,
            "shift_type": shift_type,
        })
    
    return {"staff": staff_list}


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


@router.get("/recent-check-ins")
async def get_recent_check_ins(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get recent check-ins from all staff regardless of department.
    This endpoint is for the Team attendance section on the web dashboard.
    Returns the most recent check-ins across the entire organization.
    """
    from models.db_models import Department
    
    # Get all active staff (no department filter)
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    # Join with department to get department name
    staff_query = staff_query.outerjoin(Department, User.department_id == Department.department_id)
    staff = staff_query.all()
    
    if not staff:
        return {"recent_check_ins": []}
    
    staff_ids = [u.user_id for u in staff]
    
    # Get recent check-ins from all staff
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id.in_(staff_ids),
            AttendanceLog.check_in_time >= (get_current_time() - timedelta(days=7))  # Last 7 days
        )
        .order_by(desc(AttendanceLog.check_in_time))
        .limit(limit)
        .all()
    )
    
    recent_check_ins = []
    
    for log in logs:
        # Get user information
        user = next((u for u in staff if u.user_id == log.user_id), None)
        if not user:
            continue
        
        # Calculate work hours if checked out
        work_hours = None
        if log.check_out_time:
            work_hours = (log.check_out_time - log.check_in_time).total_seconds() / 3600.0
        
        # Convert PostGIS geography to string for API response
        location_str = None
        if log.location:
            location_result = db.execute(
                text("SELECT ST_AsText(location) as location_str FROM attendance_logs WHERE attendance_log_id = :id"),
                {"id": log.attendance_log_id}
            ).first()
            if location_result:
                location_str = location_result[0]
        
        # Determine status
        status = "Checked Out" if log.check_out_time else "Active"
        
        # Get department name from the joined department
        department_name = "Unknown"
        if hasattr(user, 'department') and user.department:
            department_name = user.department.name
        elif hasattr(user, '_Department') and user._Department:
            department_name = user._Department.name
        
        recent_check_ins.append({
            "attendance_log_id": str(log.attendance_log_id),
            "user_id": str(log.user_id),
            "name": f"{user.first_name or ''} {user.surname or ''}".strip(),
            "employee_number": user.employee_number or "",
            "check_in_time": log.check_in_time.isoformat(),
            "check_out_time": log.check_out_time.isoformat() if log.check_out_time else None,
            "location": location_str,
            "work_hours": round(work_hours, 2) if work_hours else None,
            "shift_type": log.shift_type,
            "status": status,
            "department": department_name
        })
    
    return {"recent_check_ins": recent_check_ins}

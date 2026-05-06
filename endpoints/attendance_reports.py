from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, desc
from datetime import datetime, date, time, timedelta
from typing import Optional
import io
from fastapi.responses import StreamingResponse
from pdf_report_service import generate_attendance_pdf, generate_department_summary_pdf
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, AttendanceLog, Department
from timezone_config import get_current_time, to_app_timezone, timezone_aware, get_day_start, get_day_end, get_year_start, format_time, format_time_short, format_date

router = APIRouter(prefix="/reports", tags=["attendance_reports"])


@router.get("/attendance/pdf")
async def generate_attendance_pdf_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate PDF report for current user's attendance"""
    
    start = start_date or (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    
    query = db.query(AttendanceLog).filter(AttendanceLog.user_id == current_user.user_id)
    
    if start:
        try:
            start_dt = get_day_start(datetime.strptime(start, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    
    if end:
        try:
            end_dt = get_day_end(datetime.strptime(end, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")
    
    attendances = query.order_by(AttendanceLog.check_in_time).all()
    
    records = []
    for att in attendances:
        work_hours = None
        if att.check_out_time:
            check_in_naive = att.check_in_time.replace(tzinfo=None) if att.check_in_time.tzinfo else att.check_in_time
            check_out_naive = att.check_out_time.replace(tzinfo=None) if att.check_out_time.tzinfo else att.check_out_time
            work_hours = (check_out_naive - check_in_naive).total_seconds() / 3600.0
        
        records.append({
            "date": format_date(att.check_in_time),
            "check_in_time": format_time(att.check_in_time),
            "check_out_time": format_time(att.check_out_time),
            "work_hours": work_hours,
            "shift_type": att.shift_type,
            "late_reason": att.late_reason,
            "early_checkout_reason": att.early_checkout_reason,
        })
    
    summary = {
        "total_days": len(attendances),
        "present_days": len([a for a in attendances if a.check_out_time]),
        "late_days": len([a for a in attendances if a.check_in_time and a.check_in_time.hour >= 9]),
        "total_work_hours": sum(
            (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
            for a in attendances if a.check_out_time and a.check_in_time
        ),
        "total_overtime_hours": sum(
            max(0, ((a.check_out_time - a.check_in_time).total_seconds() / 3600.0 - 8))
            for a in attendances if a.check_out_time and a.check_in_time
        ),
    }
    
    user_name = f"{current_user.first_name or ''} {current_user.surname or ''}".strip()
    user_department = None
    if current_user.department_id:
        dept = db.query(Department).filter(Department.department_id == current_user.department_id).first()
        if dept:
            user_department = dept.name
    
    buffer = io.BytesIO()
    generate_attendance_pdf(
        buffer,
        records,
        start,
        end,
        user_name,
        user_department,
        summary
    )
    buffer.seek(0)
    
    filename = f"attendance_report_{start}_{end}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/attendance/pdf/{user_id}")
async def generate_user_attendance_pdf_report(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate PDF report for a specific user (HR/Admin only)"""
    
    if not current_user.role or current_user.role.role_name not in ['Admin', 'HR', 'Super Admin']:
        raise HTTPException(status_code=403, detail="Only HR and Admins can generate staff reports")
    
    try:
        target_user_id = int(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    
    target_user = db.query(User).filter(User.user_id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    start = start_date or (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    
    query = db.query(AttendanceLog).filter(AttendanceLog.user_id == target_user_id)
    
    if start:
        try:
            start_dt = get_day_start(datetime.strptime(start, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    
    if end:
        try:
            end_dt = get_day_end(datetime.strptime(end, "%Y-%m-%d"))
            query = query.filter(AttendanceLog.check_in_time <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")
    
    attendances = query.order_by(AttendanceLog.check_in_time).all()
    
    records = []
    for att in attendances:
        work_hours = None
        if att.check_out_time:
            check_in_naive = att.check_in_time.replace(tzinfo=None) if att.check_in_time.tzinfo else att.check_in_time
            check_out_naive = att.check_out_time.replace(tzinfo=None) if att.check_out_time.tzinfo else att.check_out_time
            work_hours = (check_out_naive - check_in_naive).total_seconds() / 3600.0
        
        records.append({
            "date": format_date(att.check_in_time),
            "check_in_time": format_time(att.check_in_time),
            "check_out_time": format_time(att.check_out_time),
            "work_hours": work_hours,
            "shift_type": att.shift_type,
            "late_reason": att.late_reason,
            "early_checkout_reason": att.early_checkout_reason,
        })
    
    summary = {
        "total_days": len(attendances),
        "present_days": len([a for a in attendances if a.check_out_time]),
        "late_days": len([a for a in attendances if a.check_in_time and a.check_in_time.hour >= 9]),
        "total_work_hours": sum(
            (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
            for a in attendances if a.check_out_time and a.check_in_time
        ),
        "total_overtime_hours": sum(
            max(0, ((a.check_out_time - a.check_in_time).total_seconds() / 3600.0 - 8))
            for a in attendances if a.check_out_time and a.check_in_time
        ),
    }
    
    user_name = f"{target_user.first_name or ''} {target_user.surname or ''}".strip()
    user_department = None
    if target_user.department_id:
        dept = db.query(Department).filter(Department.department_id == target_user.department_id).first()
        if dept:
            user_department = dept.name
    
    buffer = io.BytesIO()
    generate_attendance_pdf(
        buffer,
        records,
        start,
        end,
        user_name,
        user_department,
        summary
    )
    buffer.seek(0)
    
    filename = f"attendance_report_{target_user.surname or target_user.email}_{start}_{end}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/department/pdf")
async def generate_department_attendance_pdf_report(
    department_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate PDF report for department attendance summary (HR/Admin only)"""
    
    if not current_user.role or current_user.role.role_name not in ['Admin', 'HR', 'Super Admin']:
        raise HTTPException(status_code=403, detail="Only HR and Admins can generate department reports")
    
    start = start_date or (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    
    dept_name = "All Departments"
    if department_id:
        dept = db.query(Department).filter(Department.department_id == department_id).first()
        if dept:
            dept_name = dept.name
    
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    if department_id:
        staff_query = staff_query.filter(User.department_id == department_id)
    elif current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    staff_ids = [s.user_id for s in staff]
    
    try:
        start_dt = get_day_start(datetime.strptime(start, "%Y-%m-%d"))
        end_dt = get_day_end(datetime.strptime(end, "%Y-%m-%d"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    total_days = (end_dt.date() - start_dt.date()).days + 1
    
    staff_records = []
    for s in staff:
        logs = db.query(AttendanceLog).filter(
            AttendanceLog.user_id == s.user_id,
            AttendanceLog.check_in_time >= start_dt,
            AttendanceLog.check_in_time <= end_dt,
        ).all()
        
        if not logs:
            continue
        
        days_present_set = set()
        late_count = 0
        total_hours = 0
        overtime_hours = 0
        
        for log in logs:
            local_dt = to_app_timezone(log.check_in_time)
            day_key = local_dt.date()
            
            if day_key not in days_present_set:
                days_present_set.add(day_key)
                if local_dt.hour >= 9:
                    late_count += 1
            
            if log.check_out_time:
                local_checkout = to_app_timezone(log.check_out_time)
                hours = (local_checkout - local_dt).total_seconds() / 3600.0
                total_hours += hours
                if hours > 8:
                    overtime_hours += hours - 8
        
        days_present = len(days_present_set)
        attendance_pct = (days_present / total_days * 100) if total_days > 0 else 0
        
        staff_records.append({
            "staff_name": f"{s.first_name or ''} {s.surname or ''}".strip(),
            "days_present": days_present,
            "late_days": late_count,
            "total_hours": round(total_hours, 1),
            "overtime_hours": round(overtime_hours, 1),
            "attendance_percentage": round(attendance_pct, 1),
        })
    
    staff_records.sort(key=lambda x: x["staff_name"])
    
    buffer = io.BytesIO()
    generate_department_summary_pdf(
        buffer,
        staff_records,
        start,
        end,
        dept_name,
        len(staff)
    )
    buffer.seek(0)
    
    filename = f"department_attendance_{start}_{end}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
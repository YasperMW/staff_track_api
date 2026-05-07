from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, desc
from datetime import datetime, date, time, timedelta
from typing import Optional, List
from uuid import UUID
import io
from fastapi.responses import StreamingResponse
from pdf_report_service import generate_attendance_pdf, generate_department_summary_pdf
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, AttendanceLog, Department
from timezone_config import get_current_time, to_app_timezone, timezone_aware, get_day_start, get_day_end, get_year_start, format_time, format_time_short, format_date

router = APIRouter(prefix="/reports", tags=["attendance_reports"])


def _verify_report_access(current_user: User):
    allowed = ['HR', 'System Admin', 'System Administrator', 'Principal Hospital Administrator']
    if not current_user.role or current_user.role.name not in allowed:
        raise HTTPException(status_code=403, detail="Only HR and Admins can access reports")


def _build_attendance_records(attendances: List[AttendanceLog]):
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
    return records


def _build_attendance_summary(attendances: List[AttendanceLog]):
    days_with_checkout = [a for a in attendances if a.check_out_time and a.check_in_time]
    total_work = sum(
        (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
        for a in days_with_checkout
    )
    avg = total_work / len(days_with_checkout) if days_with_checkout else 0
    
    return {
        "total_days": len(attendances),
        "present_days": len([a for a in attendances if a.check_out_time]),
        "absent_days": 0,
        "on_time": len([a for a in attendances if a.check_in_time and a.check_in_time.hour < 9]),
        "late": len([a for a in attendances if a.check_in_time and a.check_in_time.hour >= 9]),
        "early_out": len([a for a in attendances if a.early_checkout_reason]),
        "total_work_hours": total_work,
        "avg_hours": avg,
    }


def _query_attendance(db: Session, user_id, start: str, end: str):
    query = db.query(AttendanceLog).filter(AttendanceLog.user_id == user_id)
    
    start_dt = get_day_start(datetime.strptime(start, "%Y-%m-%d"))
    end_dt = get_day_end(datetime.strptime(end, "%Y-%m-%d"))
    
    query = query.filter(AttendanceLog.check_in_time >= start_dt, AttendanceLog.check_in_time <= end_dt)
    return query.order_by(AttendanceLog.check_in_time).all()


def _build_department_records(db: Session, department_id: Optional[str], current_user: User, start: str, end: str):
    dept_name = "All Departments"
    if department_id:
        dept = db.query(Department).filter(Department.department_id == UUID(department_id)).first()
        if dept:
            dept_name = dept.name
    
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    if department_id:
        staff_query = staff_query.filter(User.department_id == UUID(department_id))
    elif current_user.department_id:
        staff_query = staff_query.filter(User.department_id == current_user.department_id)
    
    staff = staff_query.all()
    
    start_dt = get_day_start(datetime.strptime(start, "%Y-%m-%d"))
    end_dt = get_day_end(datetime.strptime(end, "%Y-%m-%d"))
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
        on_time_count = 0
        early_out_count = 0
        total_hours = 0
        
        for log in logs:
            local_dt = to_app_timezone(log.check_in_time)
            day_key = local_dt.date()
            
            if day_key not in days_present_set:
                days_present_set.add(day_key)
                if local_dt.hour >= 9:
                    late_count += 1
                else:
                    on_time_count += 1
            
            if log.early_checkout_reason:
                early_out_count += 1
            
            if log.check_out_time:
                local_checkout = to_app_timezone(log.check_out_time)
                hours = (local_checkout - local_dt).total_seconds() / 3600.0
                total_hours += hours
        
        days_present = len(days_present_set)
        days_absent = total_days - days_present if total_days > days_present else 0
        avg_hours = total_hours / days_present if days_present > 0 else 0
        
        staff_records.append({
            "staff_name": f"{s.first_name or ''} {s.surname or ''}".strip(),
            "days_present": days_present,
            "days_absent": days_absent,
            "on_time": on_time_count,
            "late": late_count,
            "early_out": early_out_count,
            "total_hours": round(total_hours, 1),
            "avg_hours": round(avg_hours, 1),
        })
    
    staff_records.sort(key=lambda x: x["staff_name"])
    return staff_records, dept_name, len(staff)


@router.get("/attendance")
async def get_attendance_report_json(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get individual staff attendance report data as JSON"""
    _verify_report_access(current_user)
    
    try:
        target_user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    
    target_user = db.query(User).filter(User.user_id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    start = start_date or (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    
    attendances = _query_attendance(db, target_user_id, start, end)
    records = _build_attendance_records(attendances)
    summary = _build_attendance_summary(attendances)
    
    user_department = None
    if target_user.department_id:
        dept = db.query(Department).filter(Department.department_id == target_user.department_id).first()
        if dept:
            user_department = dept.name
    
    return {
        "user_name": f"{target_user.first_name or ''} {target_user.surname or ''}".strip(),
        "department": user_department,
        "start_date": start,
        "end_date": end,
        "summary": summary,
        "records": records,
    }


@router.get("/department")
async def get_department_report_json(
    department_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get department attendance report data as JSON"""
    _verify_report_access(current_user)
    
    start = start_date or (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    
    staff_records, dept_name, total_staff = _build_department_records(db, department_id, current_user, start, end)
    
    return {
        "department_name": dept_name,
        "start_date": start,
        "end_date": end,
        "total_staff": total_staff,
        "staff_records": staff_records,
    }


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
        "absent_days": 0,
        "on_time": len([a for a in attendances if a.check_in_time and a.check_in_time.hour < 9]),
        "late": len([a for a in attendances if a.check_in_time and a.check_in_time.hour >= 9]),
        "early_out": len([a for a in attendances if a.early_checkout_reason]),
        "total_work_hours": sum(
            (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
            for a in attendances if a.check_out_time and a.check_in_time
        ),
        "avg_hours": (
            sum(
                (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
                for a in attendances if a.check_out_time and a.check_in_time
            ) / len([a for a in attendances if a.check_out_time and a.check_in_time])
        ) if len([a for a in attendances if a.check_out_time and a.check_in_time]) > 0 else 0,
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
    
    safe_name = user_name.replace(" ", "_")
    filename = f"{safe_name}_attendance_{start}_{end}.pdf"
    
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
    
    if not current_user.role or current_user.role.name not in ['HR', 'System Admin', 'System Administrator', 'Principal Hospital Administrator']:
        raise HTTPException(status_code=403, detail="Only HR and Admins can generate staff reports")
    
    try:
        target_user_id = UUID(user_id)
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
        "absent_days": 0,
        "on_time": len([a for a in attendances if a.check_in_time and a.check_in_time.hour < 9]),
        "late": len([a for a in attendances if a.check_in_time and a.check_in_time.hour >= 9]),
        "early_out": len([a for a in attendances if a.early_checkout_reason]),
        "total_work_hours": sum(
            (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
            for a in attendances if a.check_out_time and a.check_in_time
        ),
        "avg_hours": (
            sum(
                (a.check_out_time - a.check_in_time).total_seconds() / 3600.0 
                for a in attendances if a.check_out_time and a.check_in_time
            ) / len([a for a in attendances if a.check_out_time and a.check_in_time])
        ) if len([a for a in attendances if a.check_out_time and a.check_in_time]) > 0 else 0,
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
    
    safe_name = user_name.replace(" ", "_")
    filename = f"{safe_name}_attendance_{start}_{end}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/department/pdf")
async def generate_department_attendance_pdf_report(
    department_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate PDF report for department attendance summary (HR/Admin only)"""
    
    if not current_user.role or current_user.role.name not in ['HR', 'System Admin', 'System Administrator', 'Principal Hospital Administrator']:
        raise HTTPException(status_code=403, detail="Only HR and Admins can generate department reports")
    
    start = start_date or (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    end = end_date or datetime.now().strftime("%Y-%m-%d")
    
    dept_name = "All Departments"
    if department_id:
        dept = db.query(Department).filter(Department.department_id == UUID(department_id)).first()
        if dept:
            dept_name = dept.name
    
    staff_query = db.query(User).filter(User.deleted_at.is_(None))
    if department_id:
        staff_query = staff_query.filter(User.department_id == UUID(department_id))
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
            staff_records.append({
                "staff_name": f"{s.first_name or ''} {s.surname or ''}".strip(),
                "days_present": 0,
                "days_absent": total_days,
                "on_time": 0,
                "late": 0,
                "early_out": 0,
                "total_hours": 0,
                "avg_hours": 0,
            })
            continue
        
        days_present_set = set()
        late_count = 0
        on_time_count = 0
        early_out_count = 0
        total_hours = 0
        
        for log in logs:
            local_dt = to_app_timezone(log.check_in_time)
            day_key = local_dt.date()
            
            if day_key not in days_present_set:
                days_present_set.add(day_key)
                if local_dt.hour >= 9:
                    late_count += 1
                else:
                    on_time_count += 1
            
            if log.early_checkout_reason:
                early_out_count += 1
            
            if log.check_out_time:
                local_checkout = to_app_timezone(log.check_out_time)
                hours = (local_checkout - local_dt).total_seconds() / 3600.0
                total_hours += hours
        
        days_present = len(days_present_set)
        days_absent = total_days - days_present if total_days > days_present else 0
        avg_hours = total_hours / days_present if days_present > 0 else 0
        
        staff_records.append({
            "staff_name": f"{s.first_name or ''} {s.surname or ''}".strip(),
            "days_present": days_present,
            "days_absent": days_absent,
            "on_time": on_time_count,
            "late": late_count,
            "early_out": early_out_count,
            "total_hours": round(total_hours, 1),
            "avg_hours": round(avg_hours, 1),
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
    
    safe_dept_name = dept_name.replace(" ", "_")
    filename = f"{safe_dept_name}_attendance_{start}_{end}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
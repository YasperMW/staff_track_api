from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, desc, extract
from datetime import datetime, date, timedelta
from typing import Optional, List
from pydantic import BaseModel
import os
import tempfile
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from calendar import monthrange
import io

from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, AttendanceLog, Department, Role
from timezone_config import get_current_time, to_app_timezone

router = APIRouter(prefix="/reports", tags=["reports"])

class MonthlyReportRequest(BaseModel):
    year: int
    month: int
    department_id: Optional[str] = None
    user_id: Optional[str] = None

class MonthlyReportData(BaseModel):
    employee_name: str
    employee_number: str
    department: str
    total_days: int
    present_days: int
    absent_days: int
    late_days: int
    early_checkout_days: int
    total_hours: float
    average_hours: float
    attendance_records: List[dict]

def get_month_start_end(year: int, month: int) -> tuple[datetime, datetime]:
    """Get start and end datetime for a given month"""
    start_date = datetime(year, month, 1)
    last_day = monthrange(year, month)[1]
    end_date = datetime(year, month, last_day, 23, 59, 59)
    return start_date, end_date

def calculate_attendance_status(check_in_time: datetime, check_out_time: Optional[datetime]) -> str:
    """Calculate attendance status based on check-in/check-out times"""
    if not check_in_time:
        return "absent"
    
    # Convert to local timezone for comparison
    local_check_in = to_app_timezone(check_in_time)
    
    # Late if check-in after 9:00 AM
    if local_check_in.hour > 9 or (local_check_in.hour == 9 and local_check_in.minute > 0):
        status = "late"
    else:
        status = "present"
    
    # Early checkout if checked out before 16:30 (4:30 PM)
    if check_out_time:
        local_check_out = to_app_timezone(check_out_time)
        if local_check_out.hour < 16 or (local_check_out.hour == 16 and local_check_out.minute < 30):
            if status == "present":
                status = "early_checkout"
            else:
                status = "late_early_checkout"
    
    return status

@router.post("/monthly-attendance")
async def get_monthly_attendance_report(
    request: MonthlyReportRequest,
    format: str = Query("json", enum=["json", "pdf"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate monthly attendance report with optional filtering by department or individual
    """
    # Validate user permissions (only HR and above can access reports)
    allowed_roles = ["HR Admin", "System Admin", "System Administrator", "Principal Hospital Administrator", "Head of Department"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions to access reports")
    
    # Get month boundaries
    month_start, month_end = get_month_start_end(request.year, request.month)
    
    # Build base query
    query = db.query(AttendanceLog).join(User, AttendanceLog.user_id == User.user_id).join(Department, User.department_id == Department.department_id)
    
    # Apply filters
    filters = [
        AttendanceLog.check_in_time >= month_start,
        AttendanceLog.check_in_time <= month_end,
        User.deleted_at.is_(None)
    ]
    
    if request.department_id:
        filters.append(Department.department_id == request.department_id)
    
    if request.user_id:
        filters.append(User.user_id == request.user_id)
    
    # If user is Head of Department, only show their department
    if current_user.role.name == "Head of Department" and not request.department_id:
        filters.append(Department.department_id == current_user.department_id)
    
    query = query.filter(and_(*filters))
    
    # Get attendance logs
    attendance_logs = query.order_by(User.surname, User.first_name, AttendanceLog.check_in_time).all()
    
    # Group by user
    user_attendance = {}
    for log in attendance_logs:
        user_key = str(log.user.user_id)
        if user_key not in user_attendance:
            user_attendance[user_key] = {
                "user": log.user,
                "records": [],
                "total_hours": 0.0
            }
        
        # Calculate status and work hours
        status = calculate_attendance_status(log.check_in_time, log.check_out_time)
        work_hours = 0.0
        if log.check_out_time and log.check_in_time:
            work_hours = (log.check_out_time - log.check_in_time).total_seconds() / 3600.0
            user_attendance[user_key]["total_hours"] += work_hours
        
        user_attendance[user_key]["records"].append({
            "date": log.check_in_time.date(),
            "check_in_time": log.check_in_time,
            "check_out_time": log.check_out_time,
            "status": status,
            "work_hours": work_hours,
            "shift_type": log.shift_type
        })
    
    # Generate report data
    report_data = []
    total_working_days = monthrange(request.year, request.month)[1]
    
    for user_data in user_attendance.values():
        user = user_data["user"]
        records = user_data["records"]
        total_hours = user_data["total_hours"]
        
        # Calculate statistics
        present_days = len([r for r in records if r["status"] in ["present", "late", "early_checkout", "late_early_checkout"]])
        absent_days = total_working_days - present_days
        late_days = len([r for r in records if "late" in r["status"]])
        early_checkout_days = len([r for r in records if "early_checkout" in r["status"]])
        
        avg_hours = total_hours / present_days if present_days > 0 else 0.0
        
        report_data.append(MonthlyReportData(
            employee_name=f"{user.first_name} {user.surname}",
            employee_number=user.employee_number or "N/A",
            department=user.department.name if user.department else "N/A",
            total_days=total_working_days,
            present_days=present_days,
            absent_days=absent_days,
            late_days=late_days,
            early_checkout_days=early_checkout_days,
            total_hours=round(total_hours, 2),
            average_hours=round(avg_hours, 2),
            attendance_records=records
        ))
    
    if format == "pdf":
        return generate_pdf_report(report_data, request.year, request.month, request.department_id, request.user_id, db)
    
    return {
        "year": request.year,
        "month": request.month,
        "total_employees": len(report_data),
        "data": [report.dict() for report in report_data]
    }

def generate_pdf_report(
    report_data: List[MonthlyReportData],
    year: int,
    month: int,
    department_id: Optional[str],
    user_id: Optional[str],
    db: Session
) -> FileResponse:
    """Generate PDF report for monthly attendance"""
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    temp_file.close()
    
    # Create PDF document
    doc = SimpleDocTemplate(temp_file.name, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    
    # Title
    month_name = datetime(year, month, 1).strftime('%B %Y')
    title = f"Monthly Attendance Report - {month_name}"
    
    # Add department/user filter info
    subtitle = ""
    if department_id:
        dept = db.query(Department).filter(Department.department_id == department_id).first()
        subtitle = f"Department: {dept.name if dept else 'Unknown'}"
    elif user_id:
        user = db.query(User).filter(User.user_id == user_id).first()
        subtitle = f"Employee: {user.first_name} {user.surname}" if user else 'Unknown'
    else:
        subtitle = "All Departments"
    
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(subtitle, styles['Heading2']))
    elements.append(Spacer(1, 20))
    
    # Summary table
    summary_data = [["Employee Name", "Employee No.", "Department", "Present", "Absent", "Late", "Early Out", "Total Hours", "Avg Hours"]]
    
    for data in report_data:
        summary_data.append([
            data.employee_name,
            data.employee_number,
            data.department,
            str(data.present_days),
            str(data.absent_days),
            str(data.late_days),
            str(data.early_checkout_days),
            f"{data.total_hours:.1f}h",
            f"{data.average_hours:.1f}h"
        ])
    
    # Create summary table
    summary_table = Table(summary_data, repeatRows=1)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Add detailed attendance records for each employee
    for data in report_data:
        elements.append(Paragraph(f"Detailed Records - {data.employee_name}", styles['Heading3']))
        elements.append(Spacer(1, 10))
        
        # Detailed records table
        detailed_data = [["Date", "Check In", "Check Out", "Status", "Hours", "Shift"]]
        
        for record in data.attendance_records:
            check_in_str = record["check_in_time"].strftime("%H:%M") if record["check_in_time"] else "N/A"
            check_out_str = record["check_out_time"].strftime("%H:%M") if record["check_out_time"] else "N/A"
            hours_str = f"{record['work_hours']:.1f}h" if record["work_hours"] > 0 else "N/A"
            
            detailed_data.append([
                record["date"].strftime("%Y-%m-%d"),
                check_in_str,
                check_out_str,
                record["status"].replace("_", " ").title(),
                hours_str,
                record["shift_type"] or "N/A"
            ])
        
        detailed_table = Table(detailed_data, repeatRows=1)
        detailed_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(detailed_table)
        elements.append(Spacer(1, 15))
    
    # Build PDF
    doc.build(elements)
    
    # Return file response
    return FileResponse(
        temp_file.name,
        media_type="application/pdf",
        filename=f"attendance_report_{year}_{month:02d}.pdf"
    )

@router.get("/departments")
async def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of departments for filtering"""
    allowed_roles = ["HR Admin", "System Admin", "System Administrator", "Principal Hospital Administrator", "Head of Department"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    departments = db.query(Department).filter(Department.deleted_at.is_(None)).all()
    return [
        {
            "department_id": str(dept.department_id),
            "name": dept.name
        }
        for dept in departments
    ]

@router.get("/employees")
async def get_employees(
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of employees for filtering"""
    allowed_roles = ["HR Admin", "System Admin", "System Administrator", "Principal Hospital Administrator", "Head of Department"]
    if current_user.role.name not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    query = db.query(User).join(Department, User.department_id == Department.department_id).filter(User.deleted_at.is_(None))
    
    if current_user.role.name == "Head of Department":
        query = query.filter(Department.department_id == current_user.department_id)
    elif department_id:
        query = query.filter(Department.department_id == department_id)
    
    employees = query.order_by(User.surname, User.first_name).all()
    return [
        {
            "user_id": str(emp.user_id),
            "name": f"{emp.first_name} {emp.surname}",
            "employee_number": emp.employee_number,
            "department": emp.department.name if emp.department else "N/A"
        }
        for emp in employees
    ]

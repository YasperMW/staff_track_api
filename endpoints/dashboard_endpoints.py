from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc, text
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, AttendanceLog, Department, Request
from timezone_config import get_current_time

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/weekly-trend")
async def get_weekly_trend(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get attendance counts for the last 7 days"""
    today = get_current_time().date()
    start_date = today - timedelta(days=6)
    
    # Initialize counts for each day
    trend_data = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        trend_data.append({
            "label": day.strftime("%a"),
            "date": day.isoformat(),
            "value": 0
        })
    
    # Query attendance logs for the last 7 days
    logs = db.query(
        func.date(AttendanceLog.check_in_time).label('day'),
        func.count(func.distinct(AttendanceLog.user_id)).label('count')
    ).filter(
        AttendanceLog.check_in_time >= start_date
    ).group_by(
        'day'
    ).all()
    
    # Map results to trend_data
    for log in logs:
        log_date = log.day
        if isinstance(log_date, str):
            log_date = date.fromisoformat(log_date)
        
        for item in trend_data:
            if item["date"] == log_date.isoformat():
                item["value"] = log.count
                break
                
    return trend_data

@router.get("/department-distribution")
async def get_department_distribution(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get staff count distribution across departments"""
    results = db.query(
        Department.name,
        func.count(User.user_id).label('count')
    ).join(
        User, User.department_id == Department.department_id
    ).filter(
        User.deleted_at.is_(None)
    ).group_by(
        Department.name
    ).all()
    
    colors = ['#3B82F6', '#10B981', '#F59E0B', '#6366F1', '#EC4899', '#8B5CF6', '#F43F5E', '#14B8A6']
    
    distribution = []
    for i, res in enumerate(results):
        distribution.append({
            "label": res.name,
            "value": res.count,
            "color": colors[i % len(colors)]
        })
        
    return distribution

@router.get("/analytics-stats")
async def get_analytics_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get high-level analytics for the dashboard"""
    # 1. Weekly Trend Change (%)
    # Compare this week's attendance with last week's
    today = get_current_time().date()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    
    this_week_count = db.query(func.count(func.distinct(AttendanceLog.user_id))).filter(
        AttendanceLog.check_in_time >= this_week_start
    ).scalar() or 0
    
    last_week_count = db.query(func.count(func.distinct(AttendanceLog.user_id))).filter(
        and_(
            AttendanceLog.check_in_time >= last_week_start,
            AttendanceLog.check_in_time < this_week_start
        )
    ).scalar() or 0
    
    trend_change = 0
    if last_week_count > 0:
        trend_change = round(((this_week_count - last_week_count) / last_week_count) * 100)
    
    # 2. Efficiency Rate (simplified: on-time percentage for today)
    today_start = datetime.combine(today, datetime.min.time())
    
    total_today = db.query(func.count(func.distinct(AttendanceLog.user_id))).filter(
        AttendanceLog.check_in_time >= today_start
    ).scalar() or 0
    
    # Assuming on-time is before 9:00 AM as per existing logic in other endpoints
    on_time_today = db.query(func.count(func.distinct(AttendanceLog.user_id))).filter(
        and_(
            AttendanceLog.check_in_time >= today_start,
            func.extract('hour', AttendanceLog.check_in_time) < 9
        )
    ).scalar() or 0
    
    efficiency_rate = 100
    if total_today > 0:
        efficiency_rate = round((on_time_today / total_today) * 100)
    
    # 3. Active Projects (using active requests as a proxy or just a constant if not applicable)
    active_requests = db.query(func.count(Request.request_id)).filter(
        Request.status == 'pending'
    ).scalar() or 0
    
    return {
        "weekly_trend_change": trend_change,
        "efficiency_rate": efficiency_rate,
        "active_requests": active_requests
    }

@router.get("/performance-metrics")
async def get_performance_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get team performance metrics"""
    # 1. Productivity (simplified: percentage of shifts completed)
    today = get_current_time().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    total_logs = db.query(func.count(AttendanceLog.attendance_log_id)).filter(
        AttendanceLog.check_in_time >= today_start
    ).scalar() or 0
    
    completed_logs = db.query(func.count(AttendanceLog.attendance_log_id)).filter(
        and_(
            AttendanceLog.check_in_time >= today_start,
            AttendanceLog.check_out_time.isnot(None)
        )
    ).scalar() or 0
    
    productivity = 100
    if total_logs > 0:
        productivity = round((completed_logs / total_logs) * 100)
    
    # 2. Attendance (Overall rate for the month)
    first_day_of_month = today.replace(day=1)
    total_staff = db.query(func.count(User.user_id)).filter(User.deleted_at.is_(None)).scalar() or 1
    
    days_passed = (today - first_day_of_month).days + 1
    total_possible_attendance = total_staff * days_passed
    
    # Count distinct (user_id, date) pairs for attendance rate
    actual_attendance = db.query(
        func.count(func.distinct(text("user_id || '-' || date(check_in_time)")))
    ).filter(
        AttendanceLog.check_in_time >= first_day_of_month
    ).scalar() or 0
    
    attendance_rate = round((actual_attendance / total_possible_attendance) * 100) if total_possible_attendance > 0 else 0
    
    # 3. Satisfaction (Mock value as we don't have satisfaction data, or use requests approval rate)
    # Let's use approval rate of requests as a proxy for satisfaction/responsiveness
    total_processed_requests = db.query(func.count(Request.request_id)).filter(
        Request.status.in_(['approved', 'rejected'])
    ).scalar() or 0
    
    approved_requests = db.query(func.count(Request.request_id)).filter(
        Request.status == 'approved'
    ).scalar() or 0
    
    satisfaction = 95 # Default
    if total_processed_requests > 0:
        satisfaction = round((approved_requests / total_processed_requests) * 100)
    
    return {
        "productivity": productivity,
        "attendance": attendance_rate,
        "satisfaction": satisfaction
    }

@router.get("/weekly-activity")
async def get_weekly_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get weekly activity counts for check-ins, check-outs, and overtime"""
    today = get_current_time().date()
    start_of_week = today - timedelta(days=today.weekday())

    check_ins = db.query(func.count(AttendanceLog.attendance_log_id)).filter(
        AttendanceLog.check_in_time >= start_of_week
    ).scalar() or 0

    check_outs = db.query(func.count(AttendanceLog.attendance_log_id)).filter(
        and_(
            AttendanceLog.check_in_time >= start_of_week,
            AttendanceLog.check_out_time.isnot(None)
        )
    ).scalar() or 0

    overtime_logs = db.query(AttendanceLog).filter(
        and_(
            AttendanceLog.check_in_time >= start_of_week,
            AttendanceLog.check_out_time.isnot(None)
        )
    ).all()

    overtime_count = 0
    for log in overtime_logs:
        check_in_naive = log.check_in_time.replace(tzinfo=None) if log.check_in_time.tzinfo else log.check_in_time
        check_out_naive = log.check_out_time.replace(tzinfo=None) if log.check_out_time.tzinfo else log.check_out_time
        work_hours = (check_out_naive - check_in_naive).total_seconds() / 3600.0
        if work_hours > 8:
            overtime_count += 1

    return {
        "check_ins": check_ins,
        "check_outs": check_outs,
        "overtime": overtime_count
    }

@router.get("/activity-heatmap")
async def get_activity_heatmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get activity heatmap data for the last 4 weeks"""
    today = get_current_time().date()
    weeks_data = []

    for week_num in range(4):
        week_start = today - timedelta(days=today.weekday() + (week_num * 7))
        week_end = week_start + timedelta(days=6)

        daily_counts = []
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())

            count = db.query(func.count(func.distinct(AttendanceLog.user_id))).filter(
                and_(
                    AttendanceLog.check_in_time >= day_start,
                    AttendanceLog.check_in_time <= day_end
                )
            ).scalar() or 0

            daily_counts.append(count)

        weeks_data.insert(0, daily_counts)

    return {"heatmap_data": weeks_data}

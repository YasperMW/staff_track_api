"""
Centralized timezone configuration for Staff Track API
Ensures consistent timezone handling across all endpoints
"""

import pytz
from datetime import datetime, time, timedelta
from typing import Optional
import os
from functools import wraps

# Configure your timezone here - change this to your desired timezone
DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", "Africa/Blantyre")

# Create timezone object
APP_TIMEZONE = pytz.timezone(DEFAULT_TIMEZONE)

def get_current_time() -> datetime:
    """Get current timezone-aware datetime in app timezone"""
    return datetime.now(APP_TIMEZONE)

def to_app_timezone(dt: datetime) -> datetime:
    """Convert any datetime to app timezone"""
    if dt.tzinfo is None:
        # If naive datetime, assume it's UTC
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(APP_TIMEZONE)

def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC for database storage"""
    if dt.tzinfo is None:
        # If naive datetime, assume it's in app timezone
        dt = APP_TIMEZONE.localize(dt)
    return dt.astimezone(pytz.UTC)

def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """Format datetime in app timezone"""
    app_dt = to_app_timezone(dt)
    return app_dt.strftime(format_str)

def timezone_aware(func):
    """
    Decorator to ensure all datetime operations in endpoints use app timezone
    Automatically converts request datetime parameters to app timezone
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Convert any datetime parameters to app timezone
        for key, value in kwargs.items():
            if isinstance(value, datetime):
                kwargs[key] = to_app_timezone(value)
        return await func(*args, **kwargs)
    return wrapper

# Timezone constants for common operations
START_OF_DAY = time(0, 0, 0)
END_OF_DAY = time(23, 59, 59, 999999)

def get_day_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of day in app timezone"""
    if dt is None:
        dt = get_current_time()
    app_dt = to_app_timezone(dt)
    return app_dt.replace(hour=0, minute=0, second=0, microsecond=0)

def get_day_end(dt: Optional[datetime] = None) -> datetime:
    """Get end of day in app timezone"""
    if dt is None:
        dt = get_current_time()
    app_dt = to_app_timezone(dt)
    return app_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

def get_week_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of week (Monday) in app timezone"""
    if dt is None:
        dt = get_current_time()
    app_dt = to_app_timezone(dt)
    days_since_monday = app_dt.weekday()
    return get_day_start(app_dt - timedelta(days=days_since_monday))

def get_month_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of month in app timezone"""
    if dt is None:
        dt = get_current_time()
    app_dt = to_app_timezone(dt)
    return app_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def get_year_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of year in app timezone"""
    if dt is None:
        dt = get_current_time()
    app_dt = to_app_timezone(dt)
    return app_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

"""
Helper utilities for endpoints to use timezone consistently
"""

import pytz
from datetime import datetime
from fastapi import Request
from timezone_config import APP_TIMEZONE, get_current_time, to_app_timezone, to_utc

def get_request_timezone(request: Request) -> pytz.BaseTzInfo:
    """Get the app timezone from request state"""
    return getattr(request.state, 'timezone', APP_TIMEZONE)

def get_request_current_time(request: Request) -> datetime:
    """Get current time from request state or generate new one"""
    return getattr(request.state, 'current_time', get_current_time())

def timezone_endpoint(func):
    """
    Decorator for endpoints that automatically provides timezone utilities
    Adds timezone info to endpoint dependencies
    """
    def wrapper(*args, **kwargs):
        # If request is in kwargs, add timezone helpers
        if 'request' in kwargs:
            request = kwargs['request']
            kwargs['timezone'] = get_request_timezone(request)
            kwargs['current_time'] = get_request_current_time(request)
        return func(*args, **kwargs)
    return wrapper

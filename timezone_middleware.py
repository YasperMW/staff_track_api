"""
FastAPI middleware for timezone enforcement
Ensures all datetime operations use the configured timezone
"""

import time
from datetime import datetime
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from timezone_config import APP_TIMEZONE, get_current_time, to_app_timezone

class TimezoneMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce timezone handling across all endpoints
    """
    
    async def dispatch(self, request: Request, call_next):
        # Add timezone info to request state for endpoints to use
        request.state.timezone = APP_TIMEZONE
        request.state.current_time = get_current_time()
        
        # Process the request
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add timezone info to response headers
        response.headers["X-App-Timezone"] = APP_TIMEZONE.zone
        response.headers["X-Current-Time"] = get_current_time().isoformat()
        response.headers["X-Process-Time"] = str(process_time)
        
        return response

def add_timezone_middleware(app):
    """Add timezone middleware to FastAPI app"""
    app.add_middleware(TimezoneMiddleware)
    return app

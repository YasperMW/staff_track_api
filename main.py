from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from endpoints import auth_endpoints, file_endpoints, user_endpoints, lookup_endpoints, attendance_endpoints, notifications_endpoints, requests_endpoints, announcements_endpoints, holidays_endpoints, leave_endpoints, leave_policy_endpoints, notification_preferences_endpoints, reports_endpoints, shift_config_endpoints, dashboard_endpoints, attendance_reports, role_endpoints, grade_endpoints
from database import engine, seed_default_admin, run_database_migrations, seed_roles
from models.db_models import Base
import os
from dotenv import load_dotenv
from timezone_config import APP_TIMEZONE, get_current_time
from timezone_middleware import add_timezone_middleware

# Load environment variables
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

# Run database migrations (add new columns if they don't exist)
run_database_migrations()

# Seed roles before creating users
seed_roles()

# Seed default admin user if database is empty
seed_default_admin()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import asyncio
    from datetime import datetime
    from fastapi import BackgroundTasks
    from sqlalchemy.orm import Session
    from database import SessionLocal
    from endpoints.holidays_endpoints import fetch_public_holidays
    from attendance_scheduler import attendance_scheduler

    # Initialize timezone configuration
    print(f"🌍 Staff Track API initialized with timezone: {APP_TIMEZONE.zone}")
    print(f"📅 Current time in {APP_TIMEZONE.zone}: {get_current_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")

    HOLIDAYS_SYNC_ENABLED = os.getenv("HOLIDAYS_SYNC_ENABLED", "true").lower() == "true"
    HOLIDAYS_SYNC_COUNTRY = os.getenv("HOLIDAYS_SYNC_COUNTRY", "MW")

    async def _holidays_sync_loop():
        while True:
            try:
                year = datetime.now().year
                with SessionLocal() as db:
                    # Run fetch; de-dup handled inside
                    await fetch_public_holidays(year=year, country_code=HOLIDAYS_SYNC_COUNTRY, db=db)  # type: ignore
            except Exception:
                pass
            await asyncio.sleep(24 * 60 * 60)

    async def _attendance_scheduler_loop():
        """Run attendance reminder checks every minute"""
        while True:
            try:
                # Check if it's time for check-in reminders (7:30 AM), check-out reminders (4:00 PM), or late check-in alerts (9:00 AM)
                await attendance_scheduler.send_check_in_reminders()
                await attendance_scheduler.send_check_out_reminders()
                await attendance_scheduler.send_late_checkin_alerts()
            except Exception as e:
                print(f"Error in attendance scheduler: {e}")
            # Check every minute
            await asyncio.sleep(60)

    if HOLIDAYS_SYNC_ENABLED:
        asyncio.create_task(_holidays_sync_loop())
    # Start attendance scheduler
    asyncio.create_task(_attendance_scheduler_loop())
    
    yield
    
    # Shutdown (if needed)
    pass

app = FastAPI(
    title="Staff Track API",
    description="API for Staff Track Hospital Management System",
    version="1.0.0",
    lifespan=lifespan
)

# Add timezone middleware
add_timezone_middleware(app)

# Configure CORS
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_endpoints.router, prefix="/auth", tags=["auth"])
app.include_router(file_endpoints.router, prefix="/files", tags=["files"])
app.include_router(user_endpoints.router, prefix="/users", tags=["users"])
app.include_router(lookup_endpoints.router, prefix="/lookup", tags=["lookup"])
app.include_router(attendance_endpoints.router, tags=["attendance"])
app.include_router(attendance_reports.router, prefix="/attendance", tags=["attendance_reports"])
app.include_router(notifications_endpoints.router, prefix="/notifications", tags=["notifications"])
app.include_router(requests_endpoints.router)
app.include_router(announcements_endpoints.router, prefix="/api/announcements", tags=["announcements"])
app.include_router(holidays_endpoints.router, prefix="/api/holidays", tags=["holidays"])
app.include_router(leave_endpoints.router, prefix="/api", tags=["leave"])
app.include_router(leave_policy_endpoints.router, tags=["leave"])
app.include_router(notification_preferences_endpoints.router, tags=["notification-preferences"])
app.include_router(reports_endpoints.router, tags=["reports"])
app.include_router(shift_config_endpoints.router, tags=["shift-configurations"])
app.include_router(dashboard_endpoints.router)
app.include_router(role_endpoints.router)

app.include_router(grade_endpoints.router)

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
async def root():
    return {"message": "Staff Track API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8888"))  # Changed to match Flutter config
    debug = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run(app, host=host, port=port, reload=debug)

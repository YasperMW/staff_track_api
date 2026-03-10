# Timezone Configuration Guide

## Overview

The Staff Track API now enforces consistent timezone handling across all endpoints, ensuring that regardless of where the API is deployed, it will use your configured timezone for all datetime operations.

## Configuration

### 1. Set Your Timezone

Edit your `.env` file and set the `APP_TIMEZONE` variable:

```bash
APP_TIMEZONE=Africa/Blantyre
```

### 2. Available Timezones

Find your timezone at: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

Common examples:
- `Africa/Blantyre` (Malawi)
- `Africa/Johannesburg` (South Africa)
- `America/New_York` (Eastern US)
- `America/Los_Angeles` (Pacific US)
- `Europe/London` (UK)
- `Europe/Paris` (France)
- `Asia/Dubai` (UAE)
- `Asia/Kolkata` (India)
- `Australia/Sydney` (Australia)

## Implementation Details

### Centralized Configuration

The timezone system is implemented through several key files:

1. **`timezone_config.py`** - Core timezone utilities and configuration
2. **`timezone_middleware.py`** - FastAPI middleware for request-level timezone handling
3. **`endpoint_helpers.py`** - Helper functions for endpoints

### Key Features

#### Automatic Timezone Conversion
- All datetime operations automatically use your configured timezone
- Database storage uses UTC for consistency
- API responses convert back to your timezone

#### Request Context
- Each request has timezone information available in `request.state.timezone`
- Current time is available in `request.state.current_time`
- Response headers include timezone info:
  - `X-App-Timezone`: Configured timezone
  - `X-Current-Time`: Current time in app timezone

#### Utility Functions
```python
from timezone_config import (
    get_current_time,           # Current time in app timezone
    to_app_timezone,           # Convert any datetime to app timezone
    to_utc,                   # Convert datetime to UTC for storage
    get_day_start,            # Start of day in app timezone
    get_day_end,              # End of day in app timezone
    get_year_start,           # Start of year in app timezone
    format_datetime           # Format datetime in app timezone
)
```

## Usage Examples

### In Endpoints

```python
from timezone_config import get_current_time, to_utc, get_day_start

@router.get("/today-attendance")
async def get_today_attendance():
    current_time = get_current_time()
    today_start = get_day_start()
    
    # For database queries (use UTC)
    today_start_utc = to_utc(today_start)
    
    # For API responses (use app timezone)
    return {"current_time": current_time.isoformat()}
```

### With Request State

```python
@router.get("/check-time")
async def check_time(request: Request):
    timezone = request.state.timezone
    current_time = request.state.current_time
    
    return {
        "timezone": timezone.zone,
        "current_time": current_time.isoformat()
    }
```

## Database Schema

All datetime columns in the database use `DateTime(timezone=True)` to ensure proper timezone handling:

```python
created_at = Column(DateTime(timezone=True), nullable=False)
updated_at = Column(DateTime(timezone=True), nullable=False)
check_in_time = Column(DateTime(timezone=True))
```

## Scheduler Integration

The attendance scheduler automatically uses your configured timezone:

```python
from timezone_config import get_current_time, get_day_start, get_day_end

# Scheduler runs at specific times in your timezone
current_time = get_current_time()
if current_time.hour == 7 and current_time.minute == 0:
    # Send check-in reminders
```

## Migration Guide

### For Existing Code

1. Replace `datetime.utcnow()` with `get_current_time()`
2. Replace `datetime.now()` with `get_current_time()`
3. For database storage, use `to_utc(get_current_time())`
4. For API responses, use timezone-aware datetimes

### Before
```python
from datetime import datetime

# Old way - timezone unaware
now = datetime.utcnow()
user.created_at = now
```

### After
```python
from timezone_config import get_current_time, to_utc

# New way - timezone aware
now = get_current_time()
user.created_at = to_utc(now)  # Store as UTC
```

## Testing

### Verify Timezone Setup

1. Start the API server and check the console output:
```
🌍 Staff Track API initialized with timezone: Africa/Blantyre
📅 Current time in Africa/Blantyre: 2024-03-10 14:30:00 CAT
```

2. Make any API request and check response headers:
```bash
curl -I http://localhost:8888/health
```

Look for:
- `X-App-Timezone: Africa/Blantyre`
- `X-Current-Time: 2024-03-10T14:30:00+02:00`

### Test Timezone Operations

```python
# Test endpoint
GET /health

# Response headers should show your timezone
X-App-Timezone: Africa/Blantyre
X-Current-Time: 2024-03-10T14:30:00+02:00
```

## Deployment Considerations

### Environment Variables

Ensure the `APP_TIMEZONE` environment variable is set in your deployment:

```bash
# Docker
ENV APP_TIMEZONE=Africa/Blantyre

# Kubernetes
env:
- name: APP_TIMEZONE
  value: "Africa/Blantyre"

# Heroku
heroku config:set APP_TIMEZONE=Africa/Blantyre
```

### Container Timezone (Optional)

For additional consistency, you can also set the container timezone:

```dockerfile
# Dockerfile
ENV TZ=Africa/Blantyre
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
```

## Troubleshooting

### Common Issues

1. **Wrong Time Displayed**
   - Check `APP_TIMEZONE` environment variable
   - Verify timezone name is valid
   - Restart the API server

2. **Database Time Issues**
   - Ensure database connection uses UTC
   - Check that `DateTime(timezone=True)` is used in models

3. **Scheduler Not Running**
   - Verify timezone configuration in startup logs
   - Check scheduler logic uses timezone functions

### Debug Information

The API logs timezone information on startup:
```
🌍 Staff Track API initialized with timezone: Africa/Blantyre
📅 Current time in Africa/Blantyre: 2024-03-10 14:30:00 CAT
```

Response headers always include current timezone info for debugging.

## Benefits

1. **Consistency** - All datetime operations use the same timezone
2. **Deployment Independence** - Works correctly regardless of server location
3. **Database Compatibility** - Stores in UTC, displays in local timezone
4. **Scheduler Accuracy** - Reminders and notifications run at correct local times
5. **API Transparency** - Response headers show timezone information

This setup ensures your Staff Track API always operates in your timezone, no matter where it's deployed in the world.

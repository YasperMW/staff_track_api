# Staff Track API

FastAPI backend for Staff Track, a hospital staff management and attendance system. It provides
authentication, attendance tracking, leave and request workflows, reporting, notifications, and
administrative tooling for a PostgreSQL database.

## Features

- JWT authentication with password login, Google OAuth, password reset, and account lockout
- Role-based access control (System Admin, HR, Head of Department, Accountant, Staff, ...)
- Check-in / check-out with geofencing, shift configuration, and attendance reports (PDF)
- Leave balances, leave policies, and multi-level request approvals
- Announcements, push notifications (Firebase Cloud Messaging), and email notifications
- Dashboards, analytics, activity heatmaps, and user data export
- Public holiday sync, uploads, and a configurable application timezone

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy 2 with PostgreSQL (PostGIS extension)
- Pydantic v2
- Firebase Admin SDK, Resend/SMTP, ReportLab

## Requirements

- Python 3.11 or newer
- PostgreSQL 14+ with the PostGIS extension available

## Setup

1. Clone the repository and enter the project directory:

   ```bash
   git clone https://github.com/YasperMW/staff_track_api.git
   cd staff_track_api
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create the database and enable PostGIS:

   ```sql
   CREATE DATABASE staff_track;
   \c staff_track
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   ```

   The application also attempts these steps on startup if the database user has permission.

5. Copy the environment template and fill in the values:

   ```bash
   cp .env.example .env
   ```

   At minimum, set `SECRET_KEY` and `DATABASE_URL`. Generate a key with:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

6. Start the server:

   ```bash
   python main.py
   ```

   Or run Uvicorn directly:

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8888 --reload
   ```

The API is available at `http://localhost:8888`. Interactive documentation:

- Swagger UI: `http://localhost:8888/docs`
- ReDoc: `http://localhost:8888/redoc`

## Configuration

All configuration is read from environment variables (see `.env.example`).

| Variable | Description |
| --- | --- |
| `SECRET_KEY` | JWT signing key. Required. |
| `DATABASE_URL` | PostgreSQL connection URL. Required. |
| `APP_TIMEZONE` | Application timezone, e.g. `Africa/Blantyre`. |
| `CORS_ORIGINS` | Comma-separated allowed origins, or `*` for development. |
| `DEFAULT_ADMIN_EMAIL` | Email for the seeded System Admin account. |
| `DEFAULT_ADMIN_PASSWORD` | Password for the seeded admin. Generated randomly if unset. |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID. |
| `RESEND_API_KEY` / `EMAIL_*` | Email delivery credentials. |
| `FIREBASE_*` | Firebase Cloud Messaging credentials. |
| `HOLIDAYS_*` | Public holiday sync settings. |

## First Run

When the database has no users, the API seeds the required roles and a System Admin account.
Provide `DEFAULT_ADMIN_PASSWORD` before the first start, or read the randomly generated password
from the startup log, then change it after logging in.

## API Overview

| Prefix | Area |
| --- | --- |
| `/auth` | Login, registration, Google OAuth, password reset, token verification |
| `/users` | User profiles, administration, export |
| `/attendance` | Check-in/out, summaries, reports and PDFs |
| `/requests` | Leave and other request workflows with approvals |
| `/api/leave` | Leave balances and policies |
| `/notifications` | Device tokens, broadcasts, preferences |
| `/api/announcements` | Announcements |
| `/api/holidays` | Public holidays |
| `/reports`, `/dashboard` | Reporting and analytics |
| `/files`, `/uploads` | File uploads and static assets |

## Project Structure

```
staff_track_api/
├── main.py                  # Application entry point and router setup
├── database.py              # Engine, sessions, migrations, seed data
├── auth_config.py           # Auth settings
├── auth_deps.py             # Shared auth dependencies
├── timezone_config.py       # Timezone helpers
├── timezone_middleware.py   # Request timezone middleware
├── attendance_scheduler.py  # Attendance reminders
├── fcm_service.py           # Firebase Cloud Messaging
├── mail_service.py          # Email delivery
├── notification_service.py  # Notification orchestration
├── pdf_report_service.py    # PDF generation
├── rate_limiter.py          # IP rate limiting
├── endpoints/               # FastAPI routers
├── models/                  # SQLAlchemy and Pydantic models
├── migrations/              # SQL migrations
└── uploads/                 # Runtime uploads (ignored by git)
```

## Deployment Notes

- Set `DEBUG=false` and a restrictive `CORS_ORIGINS` in production.
- Run behind HTTPS and a reverse proxy.
- Never commit `.env`, Firebase service account files, or uploaded user data.
- Change seeded credentials immediately and rotate `SECRET_KEY` if it is ever exposed.
- Run database backups and restrict database network access.

## Security

This repository does not contain production credentials. If you deploy it, treat every value in
`.env` as a secret and keep it out of version control.

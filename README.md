# Staff Track API Backend

FastAPI backend for the Staff Track Hospital Management System.

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Installation

1. Navigate to the api directory:
```bash
cd api
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
```

3. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- macOS/Linux: `source venv/bin/activate`

4. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the Server

1. Start the development server:
```bash
python main.py
```

Or using uvicorn directly:
```bash
uvicorn main:app --host 0.0.0.0 --port 3000 --reload
```

2. The API will be available at: `http://localhost:3000`

### API Documentation

Once the server is running, you can access:
- Swagger UI: `http://localhost:3000/docs`
- ReDoc: `http://localhost:3000/redoc`

### Available Endpoints

#### Authentication (`/api/v1/auth`)

- `POST /login` - User login
- `POST /register` - User registration
- `POST /logout` - User logout
- `POST /reset-password` - Reset password
- `GET /verify-token` - Verify JWT token

### Demo Credentials

For testing purposes, the following demo credentials are available:

- **Admin**: `admin@hospital.com` / `admin123`
- **Any User**: Any email address with password `test123`

### Configuration

The API is configured to:
- Run on port 3000
- Accept CORS requests from any origin (for development)
- Use JWT tokens for authentication
- Store data in memory (for demo purposes)

### Production Considerations

For production deployment, consider:
- Using a real database (PostgreSQL, MySQL, etc.)
- Storing JWT secret key in environment variables
- Implementing proper CORS configuration
- Adding rate limiting
- Implementing proper logging
- Using HTTPS
- Adding input validation and sanitization

### Environment Variables

Create a `.env` file in the api directory:

```env
# JWT Configuration
SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# API Configuration
API_HOST=0.0.0.0
API_PORT=3000
DEBUG=true

# CORS Configuration
CORS_ORIGINS=*

# Database Configuration (for future use)
# DATABASE_URL=sqlite:///./staff_track.db
# DATABASE_URL=postgresql://user:password@localhost/staff_track
```

**Important:**
- Change `SECRET_KEY` to a secure, random string in production
- Set `DEBUG=false` in production
- Configure `CORS_ORIGINS` to your Flutter app's URL in production
- Add database configuration when ready to use a real database

### Project Structure

```
api/
├── main.py              # FastAPI application entry point
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (create this)
├── README.md           # This file
├── endpoints/
│   ├── __init__.py     # Endpoints package initialization
│   └── auth_endpoints.py # Authentication endpoints
└── models/
    ├── __init__.py     # Models package initialization
    └── auth_models.py  # Authentication data models
```

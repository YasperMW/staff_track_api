from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.auth_models import LoginRequest, RegisterRequest, AuthResponse, ResetPasswordRequest, OTPRequest, OTPVerifyRequest, OTPResponse, ConfirmPasswordResetRequest
from models.db_models import User, Role, Department, Designation, EmailVerification
from typing import Optional
import hashlib
import jwt
from datetime import datetime, timedelta
import uuid
import os
import random
import string
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import get_db
from mail_service import email_service
from notification_service import NotificationService

router = APIRouter()
security = HTTPBearer(auto_error=False)

# Load environment variables
load_dotenv()

# Get configuration from environment
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Mock database (in production, use a real database)
# users_db = {}
# sessions_db = {}

# Helper functions
import bcrypt

def hash_password(password: str) -> str:
    """Hash password using bcrypt with salt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_otp_code(length: int = 6) -> str:
    """Generate a random OTP code"""
    return ''.join(random.choices(string.digits, k=length))

def create_otp_record(db: Session, email: str, purpose: str) -> str:
    """Create and return OTP record"""
    # Invalidate any existing OTPs for this email and purpose
    db.query(EmailVerification).filter(
        EmailVerification.email == email,
        EmailVerification.purpose == purpose,
        EmailVerification.is_used == False
    ).update({"is_used": True})
    db.commit()
    
    # Generate new OTP
    otp_code = generate_otp_code()
    expires_at = datetime.utcnow() + timedelta(minutes=email_service.otp_expiry_minutes)
    
    # Create OTP record
    otp_record = EmailVerification(
        email=email,
        otp_code=otp_code,
        purpose=purpose,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(otp_record)
    db.commit()
    db.refresh(otp_record)
    
    return otp_code

def verify_otp_code(db: Session, email: str, otp_code: str, purpose: str) -> bool:
    """Verify OTP code"""
    otp_record = db.query(EmailVerification).filter(
        EmailVerification.email == email,
        EmailVerification.otp_code == otp_code,
        EmailVerification.purpose == purpose,
        EmailVerification.is_used == False,
        EmailVerification.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        # Update attempts for the most recent unused OTP
        recent_otp = db.query(EmailVerification).filter(
            EmailVerification.email == email,
            EmailVerification.purpose == purpose,
            EmailVerification.is_used == False
        ).order_by(EmailVerification.created_at.desc()).first()
        
        if recent_otp:
            recent_otp.attempts += 1
            recent_otp.updated_at = datetime.utcnow()
            db.commit()
        
        return False
    
    # Mark OTP as used
    otp_record.is_used = True
    otp_record.updated_at = datetime.utcnow()
    db.commit()
    
    return True

# Endpoints
@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Check against database users only
    user = db.query(User).filter(User.email == request.email).first()
    if user and verify_password(request.password, user.password_hash):
        # Check if email is verified
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email first."
            )
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        dept_name = user.department.name if user.department else ""
        token = create_access_token(data={"sub": user.email, "role": user.role.name})
        return AuthResponse(
            success=True,
            message="Login successful",
            token=token,
            user={
                "user_id": str(user.user_id),
                "email": user.email,
                "first_name": user.first_name,
                "surname": user.surname,
                "role": user.role.name,
                "department": dept_name,
                "phone": user.phone,
            }
        )
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )

@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == request.email) | (User.employee_number == request.employee_number)
    ).first()
    
    if existing_user:
        if existing_user.email == request.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        if existing_user.employee_number == request.employee_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee number already registered"
            )
    
    # Get or create role from request
    role = db.query(Role).filter(Role.name == request.role).first()
    if not role:
        role = Role(
            name=request.role,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(role)
        db.commit()
        db.refresh(role)
    
    # Get or create department from request
    department = db.query(Department).filter(Department.name == request.department).first()
    if not department:
        department = Department(
            name=request.department,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(department)
        db.commit()
        db.refresh(department)
    
    # Get or create designation from request
    designation = db.query(Designation).filter(Designation.name == request.designation_id).first()
    if not designation:
        designation = Designation(
            name=request.designation_id,
            department_id=department.department_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(designation)
        db.commit()
        db.refresh(designation)
    
    # Parse dates (API sends YYYY-MM-DD strings)
    from datetime import date
    date_of_birth_val = None
    if request.date_of_birth:
        try:
            date_of_birth_val = date.fromisoformat(request.date_of_birth)
        except ValueError:
            pass
    date_of_employment_val = None
    if request.date_of_employment:
        try:
            date_of_employment_val = date.fromisoformat(request.date_of_employment)
        except ValueError:
            pass
    
    # Create new user with pending status
    hashed_password = hash_password(request.password)
    new_user = User(
        employee_number=request.employee_number,
        national_id=request.national_id,
        suffix=request.suffix,
        first_name=request.first_name,
        surname=request.surname,
        other_names=request.other_names,
        date_of_birth=request.date_of_birth,
        gender=request.gender,
        email=request.email,
        phone=request.phone,
        home_of_origin=request.home_of_origin,
        traditional_authority=request.traditional_authority,
        district=request.district,
        current_address=request.current_address,
        marital_status=request.marital_status,
        spouse_name=request.spouse_name,
        spouse_contact=request.spouse_contact,
        date_of_employment=request.date_of_employment,
        designation_id=designation.designation_id,
        department_id=department.department_id,
        role_id=role.role_id,
        password_hash=hashed_password,
        profile_photo_url=request.profile_photo_url,
        status="pending",  # User starts as pending until email verification
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        registration_timestamp=datetime.utcnow()
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate and send OTP for email verification
    try:
        otp_code = create_otp_record(db, request.email, "registration")
        await email_service.send_account_verification_email(request.email, otp_code)
    except Exception as e:
        # If email fails, delete user and return error
        db.delete(new_user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again."
        ) from e
    
    return AuthResponse(
        success=True,
        message="Registration successful. Please check your email for verification code.",
        token=None,  # No token until email is verified
        user={
            "email": new_user.email,
            "first_name": new_user.first_name,
            "surname": new_user.surname,
            "role": new_user.role.name,
            "department": new_user.department.name if new_user.department else request.department,
            "user_id": str(new_user.user_id),
            "status": "pending",
            "phone": new_user.phone,
        }
    )

@router.post("/logout", response_model=AuthResponse)
async def logout():
    # In a real application, you would invalidate the token
    # For now, we'll just return success
    return AuthResponse(
        success=True,
        message="Logout successful"
    )

@router.post("/reset-password", response_model=OTPResponse)
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Send OTP for password reset"""
    try:
        # Check if user exists (don't reveal if not for security)
        user = db.query(User).filter(User.email == request.email).first()
        if not user:
            # Return success message anyway for security
            return OTPResponse(
                success=True,
                message="If the email exists, a password reset code has been sent",
                verified=False
            )
        
        # Generate and send OTP for password reset
        otp_code = create_otp_record(db, request.email, "password_reset")
        await email_service.send_password_reset_otp_email(request.email, otp_code)
        
        return OTPResponse(
            success=True,
            message=f"Password reset code sent to {request.email}",
            verified=False
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send password reset code"
        ) from e

def get_token_from_bearer(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[str]:
    if credentials and credentials.scheme == "Bearer":
        return credentials.credentials
    return None

@router.get("/verify-token")
async def verify_token(token: Optional[str] = Depends(get_token_from_bearer)):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        return {"valid": True, "email": email}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current authenticated user from token"""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return user
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

# OTP Verification Endpoints
@router.post("/send-otp", response_model=OTPResponse)
async def send_otp(request: OTPRequest, db: Session = Depends(get_db)):
    """Send OTP for email verification or password reset"""
    try:
        # For registration, check if user exists
        if request.purpose == "registration":
            user = db.query(User).filter(User.email == request.email).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email not found"
                )
            
            # If user is already active, don't send new OTP
            if user.status == "active":
                return OTPResponse(
                    success=True,
                    message="Email already verified",
                    verified=True
                )
        
        # Generate and send OTP
        otp_code = create_otp_record(db, request.email, request.purpose)
        await email_service.send_otp_email(request.email, otp_code, request.purpose)
        
        return OTPResponse(
            success=True,
            message=f"OTP sent to {request.email}",
            verified=False
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP"
        ) from e

@router.post("/verify-otp", response_model=OTPResponse)
async def verify_otp(request: OTPVerifyRequest, db: Session = Depends(get_db)):
    """Verify OTP code"""
    try:
        is_valid = verify_otp_code(db, request.email, request.otp_code, request.purpose)
        
        if not is_valid:
            return OTPResponse(
                success=False,
                message="Invalid or expired OTP code",
                verified=False
            )
        
        # If this is registration verification, activate the user
        if request.purpose == "registration":
            user = db.query(User).filter(User.email == request.email).first()
            if user:
                user.status = "active"
                user.updated_at = datetime.utcnow()
                db.commit()
                
                # Create default notification preferences for the user
                try:
                    NotificationService.create_default_preferences(db, str(user.user_id))
                except Exception as e:
                    print(f"Failed to create notification preferences: {e}")
                
                # Send welcome email
                try:
                    await email_service.send_welcome_email(
                        user.email, 
                        user.first_name, 
                        user.role.name
                    )
                except Exception as e:
                    # Log error but don't fail the verification
                    print(f"Failed to send welcome email: {e}")
        
        return OTPResponse(
            success=True,
            message="Email verified successfully",
            verified=True
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify OTP"
        ) from e

@router.post("/resend-otp", response_model=OTPResponse)
async def resend_otp(request: OTPRequest, db: Session = Depends(get_db)):
    """Resend OTP code"""
    try:
        # Check if there's a recent OTP (within 1 minute) to prevent spam
        recent_otp = db.query(EmailVerification).filter(
            EmailVerification.email == request.email,
            EmailVerification.purpose == request.purpose,
            EmailVerification.is_used == False,
            EmailVerification.created_at > datetime.utcnow() - timedelta(minutes=1)
        ).first()
        
        if recent_otp:
            return OTPResponse(
                success=False,
                message="Please wait before requesting another OTP",
                verified=False
            )
        
        # Generate and send new OTP
        otp_code = create_otp_record(db, request.email, request.purpose)
        await email_service.send_otp_email(request.email, otp_code, request.purpose)
        
        return OTPResponse(
            success=True,
            message=f"New OTP sent to {request.email}",
            verified=False
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend OTP"
        ) from e

@router.post("/confirm-password-reset", response_model=AuthResponse)
async def confirm_password_reset(request: ConfirmPasswordResetRequest, db: Session = Depends(get_db)):
    """Confirm password reset with OTP and new password"""
    try:
        # Verify OTP code
        is_valid = verify_otp_code(db, request.email, request.otp_code, "password_reset")
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP code"
            )
        
        # Get user and update password
        user = db.query(User).filter(User.email == request.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Hash new password and update
        user.password_hash = hash_password(request.new_password)
        user.updated_at = datetime.utcnow()
        db.commit()
        
        # Send password change confirmation email
        try:
            await email_service.send_password_reset_email(user.email, user.first_name)
        except Exception as e:
            # Log error but don't fail the password reset
            print(f"Failed to send password reset confirmation email: {e}")
        
        return AuthResponse(
            success=True,
            message="Password reset successfully",
            token=None,
            user={
                "email": user.email,
                "first_name": user.first_name,
                "surname": user.surname,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password"
        ) from e

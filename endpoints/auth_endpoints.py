from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.auth_models import LoginRequest, RegisterRequest, AuthResponse, ResetPasswordRequest, OTPRequest, OTPVerifyRequest, OTPResponse, ConfirmPasswordResetRequest, ChangePasswordRequest, GoogleAuthRequest, GoogleCheckResponse, GoogleRegisterRequest
from models.db_models import User, Role, Department, Designation, EmailVerification, Grade
from typing import Optional, List
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
from fcm_service import send_push_notification
from timezone_config import get_current_time, to_utc
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

router = APIRouter()
security = HTTPBearer(auto_error=False)

def determine_role(department_name: str, designation_name: str) -> tuple[str, bool]:
    """
    Determine user role based on department and designation.
    Returns tuple of (role_name, is_head_of_department)
    """
    dept = department_name.lower() if department_name else ""
    desig = designation_name.lower() if designation_name else ""

    # 1. System Administrator - IT dept with admin/system designation
    if "information technology" in dept or dept == "it":
        if any(k in desig for k in ["system administrator", "system admin", "network administrator", "database administrator"]):
            return "System Administrator", False
        if any(k in desig for k in ["admin", "system", "network", "it manager", "it support"]):
            return "System Admin", False

    # 2. HR Admin - HR dept with admin/manager designation
    if "human resource" in dept:
        if any(k in desig for k in ["hr admin", "hr director", "hr manager", "head of hr"]):
            return "HR Admin", False
        if any(k in desig for k in ["hr ", "human resource", "hr officer", "hr manager"]):
            return "HR", False

    # 3. Principal Hospital Administrator - Administration dept with leadership designation
    if "administration" in dept and any(k in desig for k in ["administrator", "director", "secretary", "principal", "ceo", "coo"]):
        return "Principal Hospital Administrator", False

    # 4. Accountant - Finance dept or accountant designation
    if "finance" in dept or any(k in desig for k in ["accountant", "accounts", "finance officer", "financial"]):
        return "Accountant", False

    # 5. Head of Department - leadership designation in other departments
    hod_keywords = ["head", "director", "chief", "manager", "lead", "supervisor", "principal"]
    exclude_keywords = ["administrator", "accountant", "hr ", "human resource", "system"]

    if any(k in desig for k in hod_keywords) and not any(k in desig for k in exclude_keywords):
        return "Head of Department", True

    # 6. Default: Regular Staff
    return "Staff", False

# Load environment variables
load_dotenv()

# Get configuration from environment
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")



@router.get("/grades")
async def get_grades(db: Session = Depends(get_db)):
    """Fetch all grades"""
    grades = db.query(Grade).filter(Grade.deleted_at.is_(None)).all()
    return [
        {
            "id": str(g.grade_id),
            "name": g.name,
            "annual_leave_days": g.annual_leave_days
        }
        for g in grades
    ]

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
        expire = get_current_time() + expires_delta
    else:
        expire = get_current_time() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # Convert to UTC for JWT (which expects UTC)
    expire_utc = to_utc(expire)
    to_encode.update({"exp": expire_utc})
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
    expires_at = get_current_time() + timedelta(minutes=email_service.otp_expiry_minutes)
    
    # Create OTP record
    otp_record = EmailVerification(
        email=email,
        otp_code=otp_code,
        purpose=purpose,
        expires_at=expires_at,
        created_at=get_current_time(),
        updated_at=get_current_time()
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
        EmailVerification.expires_at > get_current_time()
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
            recent_otp.updated_at = get_current_time()
            db.commit()
        
        return False
    
    # Mark OTP as used
    otp_record.is_used = True
    otp_record.updated_at = get_current_time()
    db.commit()
    
    return True

# Endpoints
MAX_FAILED_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
NOTIFY_AFTER_FAILED_ATTEMPTS = int(os.getenv("NOTIFY_AFTER_FAILED_ATTEMPTS", "3"))

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Check against database users only
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        # Check if account is locked
        if user.locked_until:
            locked_until_naive = user.locked_until.replace(tzinfo=None) if user.locked_until.tzinfo else user.locked_until
            now = get_current_time()
            if locked_until_naive > now:
                remaining_time = int((locked_until_naive - now).total_seconds() / 60)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account temporarily locked. Try again in {remaining_time} minutes."
                )

    if user and verify_password(request.password, user.password_hash):
        # Check if email is verified
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email first."
            )

        # Reset failed login attempts on successful login
        user.failed_login_attempts = 0
        user.locked_until = None

        # Update last login
        user.last_login_at = get_current_time()
        db.commit()
        db.refresh(user)
        dept_name = user.department.name if user.department else ""
        role_name = user.role.name if user.role else "Staff"
        token = create_access_token(data={"sub": user.email, "role": role_name})
        return AuthResponse(
            success=True,
            message="Login successful",
            token=token,
            user={
                "user_id": str(user.user_id),
                "email": user.email,
                "first_name": user.first_name,
                "surname": user.surname,
                "role": role_name,
                "department": dept_name,
                "phone": user.phone,
            }
        )

    # Failed login - track attempts
    if user:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        # Check if we should notify about suspicious activity
        if user.failed_login_attempts >= NOTIFY_AFTER_FAILED_ATTEMPTS:
            # Send push notification for suspicious login attempts
            if user.fcm_tokens:
                for token_record in user.fcm_tokens:
                    try:
                        await send_push_notification(
                            token=token_record.fcm_token,
                            title="Security Alert",
                            body=f"Warning: {user.failed_login_attempts} failed login attempts detected on your account",
                            data={
                                "type": "security_alert",
                                "action": "failed_login_attempts"
                            }
                        )
                    except Exception as e:
                        print(f"Failed to send push notification: {e}")

        # Lock account if too many failed attempts
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = get_current_time() + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()

            # Send account locked notification
            if user.fcm_tokens:
                for token_record in user.fcm_tokens:
                    try:
                        await send_push_notification(
                            token=token_record.fcm_token,
                            title="Account Locked",
                            body=f"Your account has been locked due to multiple failed login attempts. Try again in {LOCKOUT_MINUTES} minutes.",
                            data={
                                "type": "security_alert",
                                "action": "account_locked"
                            }
                        )
                    except Exception as e:
                        print(f"Failed to send push notification: {e}")

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked due to too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes."
            )

        db.commit()

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
    
    # Get or create department from request
    department = db.query(Department).filter(Department.name == request.department).first()
    if not department:
        department = Department(
            name=request.department,
            created_at=get_current_time(),
            updated_at=get_current_time(),
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
            created_at=get_current_time(),
            updated_at=get_current_time(),
        )
        db.add(designation)
        db.commit()
        db.refresh(designation)

    # Auto-determine role based on department and designation
    determined_role_name, is_head_of_department = determine_role(department.name, designation.name)

    # Get or create the determined role
    role = db.query(Role).filter(Role.name == determined_role_name).first()
    if not role:
        role = Role(
            name=determined_role_name,
            created_at=get_current_time(),
            updated_at=get_current_time(),
        )
        db.add(role)
        db.commit()
        db.refresh(role)
    
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
        grade_id=request.grade_id,
        role_id=role.role_id,
        is_head_of_department=is_head_of_department,  # Auto-set based on designation
        password_hash=hashed_password,
        profile_photo_url=request.profile_photo_url,
        status="pending",  # User starts as pending until email verification
        created_at=get_current_time(),
        updated_at=get_current_time(),
        registration_timestamp=get_current_time()
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
        await email_service.send_otp_email(request.email, otp_code, "password_reset")
        
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
        
        # Update last login time for token-based authentication
        # This covers page refreshes, returning to app, etc.
        user.last_login_at = get_current_time()
        db.commit()
        db.refresh(user)
        
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
                user.updated_at = get_current_time()
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
            EmailVerification.created_at > get_current_time() - timedelta(minutes=1)
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
        user.updated_at = get_current_time()
        db.commit()
        
        # Send password change confirmation email and push notification
        try:
            await email_service.send_password_reset_email(user.email, user.first_name)
        except Exception as e:
            # Log error but don't fail the password reset
            print(f"Failed to send password reset confirmation email: {e}")

        # Send push notification for password change
        try:
            if user.fcm_tokens:
                for token_record in user.fcm_tokens:
                    await send_push_notification(
                        token=token_record.fcm_token,
                        title="Password Changed",
                        body="Your password has been successfully changed. If you didn't do this, please contact support immediately.",
                        data={
                            "type": "security_alert",
                            "action": "password_changed"
                        }
                    )
        except Exception as e:
            print(f"Failed to send password change push notification: {e}")
        
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

@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change password for authenticated user"""
    try:
        # Verify current password
        if not verify_password(request.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        # Validate new password
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters long"
            )
        
        # Check if new password is same as current password
        if verify_password(request.new_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be the same as current password"
            )
        
        # Update password
        current_user.password_hash = hash_password(request.new_password)
        current_user.updated_at = get_current_time()
        db.commit()
        
        # Send password change confirmation email and push notification
        try:
            await email_service.send_password_change_email(
                current_user.email, 
                current_user.first_name
            )
        except Exception as e:
            # Log error but don't fail the password change
            print(f"Failed to send password change confirmation email: {e}")

        # Send push notification for password change
        try:
            if current_user.fcm_tokens:
                for token_record in current_user.fcm_tokens:
                    await send_push_notification(
                        token=token_record.fcm_token,
                        title="Password Changed",
                        body="Your password has been successfully changed. If you didn't do this, please contact support immediately.",
                        data={
                            "type": "security_alert",
                            "action": "password_changed"
                        }
                    )
        except Exception as e:
            print(f"Failed to send password change push notification: {e}")
        
        return AuthResponse(
            success=True,
            message="Password changed successfully",
            token=None,
            user={
                "email": current_user.email,
                "first_name": current_user.first_name,
                "surname": current_user.surname,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        ) from e


# Google OAuth Endpoints
def verify_google_token(id_token_str: str) -> dict:
    """Verify Google ID token and return user info"""
    try:
        # Verify the token using Google's public keys
        idinfo = id_token.verify_oauth2_token(id_token_str, google_requests.Request())

        # Check that the token is valid
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Invalid issuer')

        # Validate client ID if configured
        if GOOGLE_CLIENT_ID and idinfo.get('aud') != GOOGLE_CLIENT_ID:
            raise ValueError('Invalid audience - token not intended for this application')

        return {
            'google_id': idinfo['sub'],
            'email': idinfo['email'],
            'first_name': idinfo.get('given_name', ''),
            'surname': idinfo.get('family_name', ''),
            'profile_photo_url': idinfo.get('picture', ''),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {str(e)}"
        )


@router.post("/google", response_model=GoogleCheckResponse)
async def google_auth(request: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Check if Google user exists - login if exists, return data for signup if new"""
    # Verify Google token
    google_data = verify_google_token(request.id_token)

    # Check if user exists by google_id or email
    user = db.query(User).filter(
        (User.google_id == google_data['google_id']) | (User.email == google_data['email'])
    ).first()

    if user:
        # Check if account is locked
        if user.locked_until:
            locked_until_naive = user.locked_until.replace(tzinfo=None) if user.locked_until.tzinfo else user.locked_until
            now = get_current_time()
            if locked_until_naive > now:
                remaining_time = int((locked_until_naive - now).total_seconds() / 60)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account temporarily locked. Try again in {remaining_time} minutes."
                )

        # Check if user is active
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active. Please contact administrator."
            )

        # Update google_id if not set (user registered via email but now using Google)
        if not user.google_id:
            user.google_id = google_data['google_id']
            db.commit()

        # Update last login
        user.last_login_at = get_current_time()
        db.commit()
        db.refresh(user)

        # Create JWT token
        token = create_access_token(data={"sub": user.email, "role": user.role.name})

        return GoogleCheckResponse(
            exists=True,
            token=token,
            user={
                "user_id": str(user.user_id),
                "email": user.email,
                "first_name": user.first_name,
                "surname": user.surname,
                "role": user.role.name,
                "department": user.department.name if user.department else "",
                "phone": user.phone,
            },
            google_data=None
        )

    # New user - return Google data for signup form
    return GoogleCheckResponse(
        exists=False,
        token=None,
        user=None,
        google_data=google_data
    )


@router.post("/google/register", response_model=AuthResponse)
async def google_register(request: GoogleRegisterRequest, db: Session = Depends(get_db)):
    """Complete Google user registration"""
    # Verify Google token and extract user info
    google_data = verify_google_token(request.id_token)
    email = google_data['email']
    google_id = google_data['google_id']
    first_name = google_data['first_name']
    surname = google_data['surname']
    profile_photo_url = request.profile_photo_url or google_data.get('profile_photo_url')

    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == email) |
        (User.employee_number == request.employee_number) |
        (User.google_id == google_id)
    ).first()

    if existing_user:
        if existing_user.email == email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        if existing_user.employee_number == request.employee_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee number already registered"
            )
        if existing_user.google_id == google_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account already registered"
            )

    # Get or create department
    department = db.query(Department).filter(Department.name == request.department).first()
    if not department:
        department = Department(
            name=request.department,
            created_at=get_current_time(),
            updated_at=get_current_time(),
        )
        db.add(department)
        db.commit()
        db.refresh(department)

    # Get or create designation
    designation = db.query(Designation).filter(Designation.name == request.designation_id).first()
    if not designation:
        designation = Designation(
            name=request.designation_id,
            department_id=department.department_id,
            created_at=get_current_time(),
            updated_at=get_current_time(),
        )
        db.add(designation)
        db.commit()
        db.refresh(designation)

    # Auto-determine role
    determined_role_name, is_head_of_department = determine_role(department.name, designation.name)

    # Get or create role
    role = db.query(Role).filter(Role.name == determined_role_name).first()
    if not role:
        role = Role(
            name=determined_role_name,
            created_at=get_current_time(),
            updated_at=get_current_time(),
        )
        db.add(role)
        db.commit()
        db.refresh(role)

    # Create new user
    new_user = User(
        employee_number=request.employee_number,
        national_id=request.national_id,
        suffix=request.suffix,
        first_name=first_name,
        surname=surname,
        other_names=request.other_names,
        date_of_birth=request.date_of_birth,
        gender=request.gender,
        email=email,
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
        grade_id=request.grade_id,
        role_id=role.role_id,
        is_head_of_department=is_head_of_department,
        password_hash=None,  # No password for Google users
        google_id=google_id,
        profile_photo_url=profile_photo_url,
        status="active",  # Skip verification - Google verified email
        last_login_at=get_current_time(),  # Set initial login time for Google users
        created_at=get_current_time(),
        updated_at=get_current_time(),
        registration_timestamp=get_current_time()
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create default notification preferences
    try:
        NotificationService.create_default_preferences(db, str(new_user.user_id))
    except Exception as e:
        print(f"Failed to create notification preferences: {e}")

    # Send welcome email
    try:
        await email_service.send_welcome_email(
            new_user.email,
            new_user.first_name,
            new_user.role.name
        )
    except Exception as e:
        print(f"Failed to send welcome email: {e}")

    # Create JWT token
    token = create_access_token(data={"sub": new_user.email, "role": new_user.role.name})

    return AuthResponse(
        success=True,
        message="Google registration successful",
        token=token,
        user={
            "user_id": str(new_user.user_id),
            "email": new_user.email,
            "first_name": new_user.first_name,
            "surname": new_user.surname,
            "role": new_user.role.name,
            "department": new_user.department.name if new_user.department else request.department,
            "phone": new_user.phone,
        }
    )

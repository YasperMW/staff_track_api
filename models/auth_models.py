from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    employee_number: str
    national_id: str
    suffix: Optional[str] = ""
    first_name: str
    surname: str
    other_names: Optional[str] = ""
    date_of_birth: str
    gender: str
    email: EmailStr
    phone: str
    home_of_origin: str
    traditional_authority: str
    district: str
    current_address: str
    marital_status: Optional[str] = ""
    spouse_name: Optional[str] = ""
    spouse_contact: Optional[str] = ""
    date_of_employment: str
    designation_id: str
    department_id: str
    department: str
    role: Optional[str] = None  # Role is now auto-determined from department and designation
    grade_id: Optional[str] = None
    profile_photo_url: Optional[str] = None
    password: str
    confirm_password: str

# Attendance request models
class CheckInRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    device_id: Optional[str] = None
    shift_type: Optional[str] = None
    late_reason: Optional[str] = None  # Required if checking in late (after 09:00)

class CheckOutRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    device_id: Optional[str] = None
    early_checkout_reason: Optional[str] = None  # Required if checking out early (before shift end)

class AuthResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[dict] = None

class ResetPasswordRequest(BaseModel):
    email: EmailStr

class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    surname: str
    role: str
    employee_number: str
    department: str
    designation: str

class OTPRequest(BaseModel):
    email: EmailStr
    purpose: str = "registration"  # registration, password_reset

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str
    purpose: str = "registration"

class ConfirmPasswordResetRequest(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class OTPResponse(BaseModel):
    success: bool
    message: str
    verified: bool = False


# Google OAuth Models
class GoogleAuthRequest(BaseModel):
    id_token: str  # Google ID token from Flutter


class GoogleCheckResponse(BaseModel):
    exists: bool
    user: Optional[dict] = None
    google_data: Optional[dict] = None  # Pre-fill data: email, first_name, surname, photo
    token: Optional[str] = None  # JWT token if user exists


class GoogleRegisterRequest(BaseModel):
    # Google ID token (will be verified to extract google_id, email, name)
    id_token: str
    # User-provided fields
    employee_number: str
    national_id: str
    phone: str
    department: str
    department_id: str
    designation_id: str
    grade_id: Optional[str] = None
    date_of_employment: str
    date_of_birth: str
    gender: str
    home_of_origin: str
    traditional_authority: str
    district: str
    current_address: str
    # Optional fields
    suffix: Optional[str] = ""
    other_names: Optional[str] = ""
    marital_status: Optional[str] = ""
    spouse_name: Optional[str] = ""
    spouse_contact: Optional[str] = ""
    profile_photo_url: Optional[str] = None  # Override Google photo if provided

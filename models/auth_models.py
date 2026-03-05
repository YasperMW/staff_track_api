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

class CheckOutRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    device_id: Optional[str] = None

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

class OTPResponse(BaseModel):
    success: bool
    message: str
    verified: bool = False

from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)

class RegisterRequest(BaseModel):
    employee_number: str = Field(max_length=50)
    national_id: str = Field(max_length=50)
    suffix: Optional[str] = Field(default="", max_length=20)
    first_name: str = Field(max_length=100)
    surname: str = Field(max_length=100)
    other_names: Optional[str] = Field(default="", max_length=150)
    date_of_birth: str = Field(max_length=10)
    gender: str = Field(max_length=10)
    email: EmailStr
    phone: str = Field(max_length=30)
    home_of_origin: str = Field(max_length=150)
    traditional_authority: str = Field(max_length=100)
    district: str = Field(max_length=100)
    current_address: str = Field(max_length=500)
    marital_status: Optional[str] = Field(default="", max_length=20)
    spouse_name: Optional[str] = Field(default="", max_length=150)
    spouse_contact: Optional[str] = Field(default="", max_length=30)
    date_of_employment: str = Field(max_length=10)
    designation_id: str = Field(max_length=36)
    department_id: str = Field(max_length=36)
    department: str = Field(max_length=150)
    role: Optional[str] = Field(default=None, max_length=100)
    grade_id: Optional[str] = Field(default=None, max_length=36)
    profile_photo_url: Optional[str] = Field(default=None, max_length=500)
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)

class CheckInRequest(BaseModel):
    location: Optional[str] = Field(default=None, max_length=500)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    device_id: Optional[str] = Field(default=None, max_length=200)
    shift_type: Optional[str] = Field(default=None, max_length=50)
    late_reason: Optional[str] = Field(default=None, max_length=500)

class CheckOutRequest(BaseModel):
    location: Optional[str] = Field(default=None, max_length=500)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    device_id: Optional[str] = Field(default=None, max_length=200)
    early_checkout_reason: Optional[str] = Field(default=None, max_length=500)

class AuthResponse(BaseModel):
    success: bool
    message: str = Field(max_length=500)
    token: Optional[str] = Field(default=None, max_length=2000)
    user: Optional[dict] = None

class ResetPasswordRequest(BaseModel):
    email: EmailStr

class UserResponse(BaseModel):
    id: str = Field(max_length=36)
    email: str = Field(max_length=255)
    first_name: str = Field(max_length=100)
    surname: str = Field(max_length=100)
    role: str = Field(max_length=100)
    employee_number: str = Field(max_length=50)
    department: str = Field(max_length=150)
    designation: str = Field(max_length=150)

class OTPRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(default="registration", max_length=20)

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(max_length=6)
    purpose: str = Field(default="registration", max_length=20)

class ConfirmPasswordResetRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(max_length=6)
    new_password: str = Field(max_length=128)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)

class OTPResponse(BaseModel):
    success: bool
    message: str = Field(max_length=500)
    verified: bool = False


# Google OAuth Models
class GoogleAuthRequest(BaseModel):
    id_token: str = Field(max_length=2000)


class GoogleCheckResponse(BaseModel):
    exists: bool
    user: Optional[dict] = None
    google_data: Optional[dict] = None
    token: Optional[str] = Field(default=None, max_length=2000)


class GoogleRegisterRequest(BaseModel):
    id_token: str = Field(max_length=2000)
    employee_number: str = Field(max_length=50)
    national_id: str = Field(max_length=50)
    phone: str = Field(max_length=30)
    department: str = Field(max_length=150)
    department_id: str = Field(max_length=36)
    designation_id: str = Field(max_length=36)
    grade_id: Optional[str] = Field(default=None, max_length=36)
    date_of_employment: str = Field(max_length=10)
    date_of_birth: str = Field(max_length=10)
    gender: str = Field(max_length=10)
    home_of_origin: str = Field(max_length=150)
    traditional_authority: str = Field(max_length=100)
    district: str = Field(max_length=100)
    current_address: str = Field(max_length=500)
    suffix: Optional[str] = Field(default="", max_length=20)
    other_names: Optional[str] = Field(default="", max_length=150)
    marital_status: Optional[str] = Field(default="", max_length=20)
    spouse_name: Optional[str] = Field(default="", max_length=150)
    spouse_contact: Optional[str] = Field(default="", max_length=30)
    profile_photo_url: Optional[str] = Field(default=None, max_length=500)

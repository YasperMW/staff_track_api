from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from database import get_db
from models.db_models import User, Role, Department, EmployeeFile
from datetime import datetime, timedelta
import jwt
import os
import bcrypt
from dotenv import load_dotenv

router = APIRouter()
security = HTTPBearer(auto_error=False)

# Pydantic models for response
class UserResponse(BaseModel):
    user_id: str
    employee_number: str
    national_id: Optional[str]
    first_name: str
    surname: str
    other_names: Optional[str]
    suffix: Optional[str]
    date_of_birth: Optional[str]
    gender: Optional[str]
    home_of_origin: Optional[str]
    traditional_authority: Optional[str]
    district: Optional[str]
    current_address: Optional[str]
    contact_number: Optional[str]
    email: str
    marital_status: Optional[str]
    spouse_name: Optional[str]
    spouse_contact: Optional[str]
    date_of_employment: Optional[str]
    designation: Optional[str]
    department_id: Optional[str]
    is_head_of_department: bool
    phone: Optional[str]
    role_id: str
    status: str
    profile_photo_url: Optional[str]
    blacklisted_at: Optional[str]
    blacklisted_reason: Optional[str]
    registration_timestamp: Optional[str]
    selfie_verified: bool
    last_login_at: Optional[str]
    failed_login_attempts: Optional[int]
    locked_until: Optional[str]
    created_at: str
    updated_at: str
    deleted_at: Optional[str]
    deleted_by: Optional[str]
    role_name: str
    department_name: Optional[str]

    class Config:
        from_attributes = True

class UserProfileResponse(BaseModel):
    user_id: str
    employee_number: str
    first_name: str
    surname: str
    other_names: Optional[str]
    email: str
    phone: Optional[str]
    role_name: str
    department_name: Optional[str]
    designation: Optional[str]
    status: str
    profile_photo_url: Optional[str]
    last_login_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True

class CompleteUserProfileResponse(BaseModel):
    user_id: str
    employee_number: str
    national_id: Optional[str]
    first_name: str
    surname: str
    other_names: Optional[str]
    suffix: Optional[str]
    date_of_birth: Optional[str]
    gender: Optional[str]
    home_of_origin: Optional[str]
    traditional_authority: Optional[str]
    district: Optional[str]
    current_address: Optional[str]
    contact_number: Optional[str]
    email: str
    marital_status: Optional[str]
    spouse_name: Optional[str]
    spouse_contact: Optional[str]
    date_of_employment: Optional[str]
    designation_id: Optional[str]
    department_id: Optional[str]
    is_head_of_department: bool
    phone: Optional[str]
    role_id: str
    status: str
    profile_photo_url: Optional[str]
    blacklisted_at: Optional[str]
    blacklisted_reason: Optional[str]
    registration_timestamp: Optional[str]
    selfie_verified: bool
    last_login_at: Optional[str]
    created_at: str
    updated_at: str
    deleted_at: Optional[str]
    deleted_by: Optional[str]
    role_name: str
    department_name: Optional[str]
    designation_name: Optional[str]
    grade_id: Optional[str]
    grade_name: Optional[str]

    class Config:
        from_attributes = True

class UsersListResponse(BaseModel):
    success: bool
    message: str
    users: List[UserResponse]
    total_count: int

class DocumentResponse(BaseModel):
    document_id: str
    user_id: str
    document_type: str
    file_path: str
    file_name: str
    upload_date: str
    
    class Config:
        from_attributes = True

class UserDetailsResponse(BaseModel):
    user: UserResponse
    documents: List[DocumentResponse]

class LockAccountRequest(BaseModel):
    lock_duration_minutes: Optional[int] = None
    password_confirmation: str

class DeleteAccountRequest(BaseModel):
    password_confirmation: str

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class UpdateProfilePhotoRequest(BaseModel):
    profile_photo_url: str

# Helper function to get token from Bearer header
def get_token_from_bearer(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[str]:
    if credentials and credentials.scheme == "Bearer":
        return credentials.credentials
    return None

# Helper function to extract email from JWT token
def get_email_from_token(token: str) -> Optional[str]:
    try:
        import jwt
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
        ALGORITHM = os.getenv("ALGORITHM", "HS256")
        
        print(f"Decoding token with algorithm: {ALGORITHM}")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"Token payload: {payload}")
        email: str = payload.get("sub")
        print(f"Extracted email: {email}")
        return email
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None

# Helper function to verify admin role (optional - you may want to restrict access)
def verify_admin_role(token: str) -> bool:
    try:
        import jwt
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
        ALGORITHM = os.getenv("ALGORITHM", "HS256")
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role: str = payload.get("role")
        # Updated with actual role names from database
        return user_role in ["HR", "HR Admin", "System Admin", "System Administrator", "Principal Hospital Administrator", "Head of Department", "Accountant"]
    except:
        return False

@router.get("/debug-token")
async def debug_token(
    token: Optional[str] = Depends(get_token_from_bearer)
):
    """
    Debug endpoint to check token payload
    """
    if not token:
        return {"error": "No token provided"}
    
    try:
        import jwt
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
        ALGORITHM = os.getenv("ALGORITHM", "HS256")
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "payload": payload,
            "role": payload.get("role"),
            "is_admin": verify_admin_role(token)
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/test")
async def test_endpoint():
    """Simple test endpoint to check if the router is working"""
    return {"message": "User endpoints are working", "status": "ok"}

@router.get("/profile", response_model=UserProfileResponse)
async def get_current_user_profile(
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get the profile of the currently authenticated user.
    """
    print(f"Profile endpoint called with token: {token is not None}")
    
    # Verify authentication
    if not token:
        print("No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Extract email from token
    email = get_email_from_token(token)
    if not email:
        print("Could not extract email from token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token - could not extract user information"
        )
    
    try:
        print(f"Querying user with email: {email}")
        # Query user by email without joins first
        user = db.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            print(f"User not found with email: {email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        print(f"Found user: {user.first_name} {user.surname}")
        
        # Get role, department, and designation separately to avoid join issues
        role_name = "Unknown"
        department_name = None
        designation_name = None
        
        try:
            if user.role_id:
                role = db.query(Role).filter(Role.role_id == user.role_id).first()
                if role:
                    role_name = role.name
        except Exception as e:
            print(f"Error getting role: {e}")
        
        try:
            if user.department_id:
                department = db.query(Department).filter(Department.department_id == user.department_id).first()
                if department:
                    department_name = department.name
                    print(f"Found department: {department_name}")
                else:
                    print(f"No department found for department_id: {user.department_id}")
            else:
                print(f"User has no department_id")
        except Exception as e:
            print(f"Error getting department: {e}")
        
        try:
            if user.designation_id:
                from models.db_models import Designation
                designation = db.query(Designation).filter(Designation.designation_id == user.designation_id).first()
                if designation:
                    designation_name = designation.name
        except Exception as e:
            print(f"Error getting designation: {e}")
        
        # Return user profile data
        profile_data = {
            "user_id": str(user.user_id),
            "employee_number": user.employee_number,
            "first_name": user.first_name,
            "surname": user.surname,
            "other_names": user.other_names,
            "email": user.email,
            "phone": user.phone,
            "role_name": role_name,
            "department_name": department_name,
            "designation": designation_name,
            "status": user.status,
            "profile_photo_url": user.profile_photo_url,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        print(f"Profile response data: {profile_data}")
        return UserProfileResponse(**profile_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user profile: {str(e)}"
        )

@router.get("/profile/complete", response_model=CompleteUserProfileResponse)
async def get_complete_user_profile(
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get the complete profile of the currently authenticated user.
    Returns all information submitted during account creation.
    """
    print(f"Complete profile endpoint called with token: {token is not None}")
    
    # Verify authentication
    if not token:
        print("No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Extract email from token
    email = get_email_from_token(token)
    if not email:
        print("Could not extract email from token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token - could not extract user information"
        )
    
    try:
        print(f"Querying complete user profile with email: {email}")
        # Query user with all relationships
        user = db.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            print(f"User not found with email: {email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        print(f"Found complete user: {user.first_name} {user.surname}")
        
        # Get related information
        role_name = user.role.name if user.role else "Unknown"
        department_name = user.department.name if user.department else None
        designation_name = user.designation.name if user.designation else None
        grade_name = user.grade.name if user.grade else None
        
        # Return complete user profile data
        profile_data = {
            "user_id": str(user.user_id),
            "employee_number": user.employee_number,
            "national_id": user.national_id,
            "first_name": user.first_name,
            "surname": user.surname,
            "other_names": user.other_names,
            "suffix": user.suffix,
            "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "gender": user.gender,
            "home_of_origin": user.home_of_origin,
            "traditional_authority": user.traditional_authority,
            "district": user.district,
            "current_address": user.current_address,
            "contact_number": user.contact_number,
            "email": user.email,
            "marital_status": user.marital_status,
            "spouse_name": user.spouse_name,
            "spouse_contact": user.spouse_contact,
            "date_of_employment": user.date_of_employment.isoformat() if user.date_of_employment else None,
            "designation_id": str(user.designation_id) if user.designation_id else None,
            "department_id": str(user.department_id) if user.department_id else None,
            "is_head_of_department": user.is_head_of_department,
            "phone": user.phone,
            "role_id": str(user.role_id),
            "status": user.status,
            "profile_photo_url": user.profile_photo_url,
            "blacklisted_at": user.blacklisted_at.isoformat() if user.blacklisted_at else None,
            "blacklisted_reason": user.blacklisted_reason,
            "registration_timestamp": user.registration_timestamp.isoformat() if user.registration_timestamp else None,
            "selfie_verified": user.selfie_verified,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
            "deleted_by": str(user.deleted_by) if user.deleted_by else None,
            "role_name": role_name,
            "department_name": department_name,
            "designation_name": designation_name,
            "grade_id": str(user.grade_id) if user.grade_id else None,
            "grade_name": grade_name
        }
        print(f"Complete profile response data prepared with {len([k for k, v in profile_data.items() if v is not None])} fields")
        return CompleteUserProfileResponse(**profile_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving complete user profile: {str(e)}"
        )

@router.post("/profile/update-photo")
async def update_profile_photo(
    request: UpdateProfilePhotoRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Update the profile photo URL of the currently authenticated user.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    email = get_email_from_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.profile_photo_url = request.profile_photo_url
        user.updated_at = datetime.utcnow()
        db.commit()
        
        return {"success": True, "message": "Profile photo updated successfully", "profile_photo_url": request.profile_photo_url}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating profile photo: {str(e)}"
        )

@router.get("/users", response_model=UsersListResponse)
async def get_all_users(
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get all users from the database.
    Returns comprehensive user data including roles and departments.
    """
    # Verify authentication (optional - remove if you want public access)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Verify admin role (optional - remove if you want all authenticated users to access)
    if not verify_admin_role(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access user data"
        )
    
    try:
        # Query all users including their roles and departments with explicit join conditions
        users = db.query(User).join(Role, User.role_id == Role.role_id).outerjoin(Department, User.department_id == Department.department_id).all()
        
        user_responses = []
        for user in users:
            user_data = UserResponse(
                user_id=str(user.user_id),
                employee_number=user.employee_number,
                national_id=user.national_id,
                first_name=user.first_name,
                surname=user.surname,
                other_names=user.other_names,
                suffix=user.suffix,
                date_of_birth=user.date_of_birth.isoformat() if user.date_of_birth else None,
                gender=user.gender,
                home_of_origin=user.home_of_origin,
                traditional_authority=user.traditional_authority,
                district=user.district,
                current_address=user.current_address,
                contact_number=user.contact_number,
                email=user.email,
                marital_status=user.marital_status,
                spouse_name=user.spouse_name,
                spouse_contact=user.spouse_contact,
                date_of_employment=user.date_of_employment.isoformat() if user.date_of_employment else None,
                designation=user.designation.name if user.designation else None,
                department_id=str(user.department_id) if user.department_id else None,
                is_head_of_department=user.is_head_of_department,
                phone=user.phone,
                role_id=str(user.role_id),
                status=user.status,
                profile_photo_url=user.profile_photo_url,
                blacklisted_at=user.blacklisted_at.isoformat() if user.blacklisted_at else None,
                blacklisted_reason=user.blacklisted_reason,
                registration_timestamp=user.registration_timestamp.isoformat() if user.registration_timestamp else None,
                selfie_verified=user.selfie_verified,
                last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
                failed_login_attempts=user.failed_login_attempts,
                locked_until=user.locked_until.isoformat() if user.locked_until else None,
                created_at=user.created_at.isoformat() if user.created_at else None,
                updated_at=user.updated_at.isoformat() if user.updated_at else None,
                deleted_at=user.deleted_at.isoformat() if user.deleted_at else None,
                deleted_by=str(user.deleted_by) if user.deleted_by else None,
                role_name=user.role.name if user.role else "Unknown",
                department_name=user.department.name if user.department else None
            )
            user_responses.append(user_data)
        
        return UsersListResponse(
            success=True,
            message=f"Successfully retrieved {len(user_responses)} users",
            users=user_responses,
            total_count=len(user_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving users: {str(e)}"
        )

@router.get("/users/active", response_model=UsersListResponse)
async def get_active_users(
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get only active (non-deleted) users from the database.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    if not verify_admin_role(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access user data"
        )
    
    try:
        # Query only active users (not deleted) with explicit join conditions
        users = db.query(User).join(Role, User.role_id == Role.role_id).outerjoin(Department, User.department_id == Department.department_id).filter(
            User.deleted_at.is_(None)
        ).all()
        
        print(f"Query executed successfully, found {len(users)} users")
        
        user_responses = []
        for user in users:
            user_data = UserResponse(
                user_id=str(user.user_id),
                employee_number=user.employee_number,
                national_id=user.national_id,
                first_name=user.first_name,
                surname=user.surname,
                other_names=user.other_names,
                suffix=user.suffix,
                date_of_birth=user.date_of_birth.isoformat() if user.date_of_birth else None,
                gender=user.gender,
                home_of_origin=user.home_of_origin,
                traditional_authority=user.traditional_authority,
                district=user.district,
                current_address=user.current_address,
                contact_number=user.contact_number,
                email=user.email,
                marital_status=user.marital_status,
                spouse_name=user.spouse_name,
                spouse_contact=user.spouse_contact,
                date_of_employment=user.date_of_employment.isoformat() if user.date_of_employment else None,
                designation=user.designation.name if user.designation else None,
                department_id=str(user.department_id) if user.department_id else None,
                is_head_of_department=user.is_head_of_department,
                phone=user.phone,
                role_id=str(user.role_id),
                status=user.status,
                profile_photo_url=user.profile_photo_url,
                blacklisted_at=user.blacklisted_at.isoformat() if user.blacklisted_at else None,
                blacklisted_reason=user.blacklisted_reason,
                registration_timestamp=user.registration_timestamp.isoformat() if user.registration_timestamp else None,
                selfie_verified=user.selfie_verified,
                last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
                failed_login_attempts=user.failed_login_attempts,
                locked_until=user.locked_until.isoformat() if user.locked_until else None,
                created_at=user.created_at.isoformat() if user.created_at else None,
                updated_at=user.updated_at.isoformat() if user.updated_at else None,
                deleted_at=user.deleted_at.isoformat() if user.deleted_at else None,
                deleted_by=str(user.deleted_by) if user.deleted_by else None,
                role_name=user.role.name if user.role else "Unknown",
                department_name=user.department.name if user.department else None
            )
            user_responses.append(user_data)
        
        return UsersListResponse(
            success=True,
            message=f"Successfully retrieved {len(user_responses)} active users",
            users=user_responses,
            total_count=len(user_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving active users: {str(e)}"
        )

@router.get("/users/by-department/{department_name}", response_model=UsersListResponse)
async def get_users_by_department(
    department_name: str,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get users filtered by department name.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    if not verify_admin_role(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access user data"
        )
    
    try:
        # Query users by department
        users = db.query(User).join(Role).join(Department).filter(
            Department.name == department_name,
            User.deleted_at.is_(None)
        ).all()
        
        user_responses = []
        for user in users:
            user_data = UserResponse(
                user_id=str(user.user_id),
                employee_number=user.employee_number,
                national_id=user.national_id,
                first_name=user.first_name,
                surname=user.surname,
                other_names=user.other_names,
                suffix=user.suffix,
                date_of_birth=user.date_of_birth.isoformat() if user.date_of_birth else None,
                gender=user.gender,
                home_of_origin=user.home_of_origin,
                traditional_authority=user.traditional_authority,
                district=user.district,
                current_address=user.current_address,
                contact_number=user.contact_number,
                email=user.email,
                marital_status=user.marital_status,
                spouse_name=user.spouse_name,
                spouse_contact=user.spouse_contact,
                date_of_employment=user.date_of_employment.isoformat() if user.date_of_employment else None,
                designation=user.designation.name if user.designation else None,
                department_id=str(user.department_id) if user.department_id else None,
                is_head_of_department=user.is_head_of_department,
                phone=user.phone,
                role_id=str(user.role_id),
                status=user.status,
                profile_photo_url=user.profile_photo_url,
                blacklisted_at=user.blacklisted_at.isoformat() if user.blacklisted_at else None,
                blacklisted_reason=user.blacklisted_reason,
                registration_timestamp=user.registration_timestamp.isoformat() if user.registration_timestamp else None,
                selfie_verified=user.selfie_verified,
                last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
                failed_login_attempts=user.failed_login_attempts,
                locked_until=user.locked_until.isoformat() if user.locked_until else None,
                created_at=user.created_at.isoformat() if user.created_at else None,
                updated_at=user.updated_at.isoformat() if user.updated_at else None,
                deleted_at=user.deleted_at.isoformat() if user.deleted_at else None,
                deleted_by=str(user.deleted_by) if user.deleted_by else None,
                role_name=user.role.name if user.role else "Unknown",
                department_name=user.department.name if user.department else None
            )
            user_responses.append(user_data)
        
        return UsersListResponse(
            success=True,
            message=f"Successfully retrieved {len(user_responses)} users from {department_name} department",
            users=user_responses,
            total_count=len(user_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving users by department: {str(e)}"
        )

class UpdateUserRoleRequest(BaseModel):
    role_id: str

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: UpdateUserRoleRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Update a user's role. Only accessible by System Admins.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Verify system admin role specifically
    try:
        import jwt
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
        ALGORITHM = os.getenv("ALGORITHM", "HS256")
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role: str = payload.get("role")
        
        # Only allow System Admins to change roles
        if not user_role or not user_role.lower() in ['system admin', 'system administrator']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only System Admins can change user roles"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token"
        )
    
    try:
        # Get the user to update
        user = db.query(User).filter(
            User.user_id == user_id,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get the new role
        new_role = db.query(Role).filter(Role.role_id == request.role_id).first()
        
        if not new_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )
        
        # Update user role
        old_role_name = user.role.name if user.role else "Unknown"
        user.role_id = request.role_id
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        # Log the role change (you might want to add an audit log table)
        print(f"User {user.first_name} {user.surname} role changed from {old_role_name} to {new_role.name} by System Admin")
        
        # Return updated user data
        user_data = UserResponse(
            user_id=str(user.user_id),
            employee_number=user.employee_number,
            national_id=user.national_id,
            first_name=user.first_name,
            surname=user.surname,
            other_names=user.other_names,
            suffix=user.suffix,
            date_of_birth=user.date_of_birth.isoformat() if user.date_of_birth else None,
            gender=user.gender,
            home_of_origin=user.home_of_origin,
            traditional_authority=user.traditional_authority,
            district=user.district,
            current_address=user.current_address,
            contact_number=user.contact_number,
            email=user.email,
            marital_status=user.marital_status,
            spouse_name=user.spouse_name,
            spouse_contact=user.spouse_contact,
            date_of_employment=user.date_of_employment.isoformat() if user.date_of_employment else None,
            designation=user.designation.name if user.designation else None,
            department_id=str(user.department_id) if user.department_id else None,
            is_head_of_department=user.is_head_of_department,
            phone=user.phone,
            role_id=str(user.role_id),
            status=user.status,
            profile_photo_url=user.profile_photo_url,
            blacklisted_at=user.blacklisted_at.isoformat() if user.blacklisted_at else None,
            blacklisted_reason=user.blacklisted_reason,
            registration_timestamp=user.registration_timestamp.isoformat() if user.registration_timestamp else None,
            selfie_verified=user.selfie_verified,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            failed_login_attempts=user.failed_login_attempts,
            locked_until=user.locked_until.isoformat() if user.locked_until else None,
            created_at=user.created_at.isoformat() if user.created_at else None,
            updated_at=user.updated_at.isoformat() if user.updated_at else None,
            deleted_at=user.deleted_at.isoformat() if user.deleted_at else None,
            deleted_by=str(user.deleted_by) if user.deleted_by else None,
            role_name=user.role.name if user.role else "Unknown",
            department_name=user.department.name if user.department else None
        )
        
        return {
            "success": True,
            "message": f"User role updated successfully from {old_role_name} to {new_role.name}",
            "data": user_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error updating user role: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user role: {str(e)}"
        )

@router.get("/users/{user_id}", response_model=UserDetailsResponse)
async def get_user_details(
    user_id: str,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get detailed information for a specific user including their documents.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    if not verify_admin_role(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access user details"
        )
    
    try:
        # Query user with their role and department
        user = db.query(User).join(Role, User.role_id == Role.role_id).outerjoin(Department, User.department_id == Department.department_id).filter(
            User.user_id == user_id,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Query user documents
        documents = db.query(EmployeeFile).filter(
            EmployeeFile.user_id == user_id,
            EmployeeFile.deleted_at.is_(None)
        ).all()
        
        # Prepare user response
        user_data = UserResponse(
            user_id=str(user.user_id),
            employee_number=user.employee_number,
            national_id=user.national_id,
            first_name=user.first_name,
            surname=user.surname,
            other_names=user.other_names,
            suffix=user.suffix,
            date_of_birth=user.date_of_birth.isoformat() if user.date_of_birth else None,
            gender=user.gender,
            home_of_origin=user.home_of_origin,
            traditional_authority=user.traditional_authority,
            district=user.district,
            current_address=user.current_address,
            contact_number=user.contact_number,
            email=user.email,
            marital_status=user.marital_status,
            spouse_name=user.spouse_name,
            spouse_contact=user.spouse_contact,
            date_of_employment=user.date_of_employment.isoformat() if user.date_of_employment else None,
            designation=user.designation.name if user.designation else None,
            department_id=str(user.department_id) if user.department_id else None,
            is_head_of_department=user.is_head_of_department,
            phone=user.phone,
            role_id=str(user.role_id),
            status=user.status,
            profile_photo_url=user.profile_photo_url,
            blacklisted_at=user.blacklisted_at.isoformat() if user.blacklisted_at else None,
            blacklisted_reason=user.blacklisted_reason,
            registration_timestamp=user.registration_timestamp.isoformat() if user.registration_timestamp else None,
            selfie_verified=user.selfie_verified,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            failed_login_attempts=user.failed_login_attempts,
            locked_until=user.locked_until.isoformat() if user.locked_until else None,
            created_at=user.created_at.isoformat() if user.created_at else None,
            updated_at=user.updated_at.isoformat() if user.updated_at else None,
            deleted_at=user.deleted_at.isoformat() if user.deleted_at else None,
            deleted_by=str(user.deleted_by) if user.deleted_by else None,
            role_name=user.role.name if user.role else "Unknown",
            department_name=user.department.name if user.department else None
        )
        
        # Prepare documents response
        document_responses = []
        for doc in documents:
            doc_data = DocumentResponse(
                document_id=str(doc.employee_file_id),
                user_id=str(doc.user_id),
                document_type=doc.file_type,
                file_path=doc.file_url,
                file_name=doc.original_filename or 'Unknown',
                upload_date=doc.upload_date.isoformat() if doc.upload_date else None
            )
            document_responses.append(doc_data)
        
        return UserDetailsResponse(
            user=user_data,
            documents=document_responses
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user details: {str(e)}"
        )

@router.put("/users/{user_id}/lock", response_model=ApiResponse)
async def lock_user_account(
    user_id: str,
    request: LockAccountRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    load_dotenv()
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
    ALGORITHM = os.getenv("ALGORITHM", "HS256")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_role: str = payload.get("role")
        if not admin_role or not admin_role.lower() in ['system admin', 'system administrator']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only System Admins can lock accounts")
        admin_email: str = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid authentication token")

    admin_user = db.query(User).filter(User.email == admin_email, User.deleted_at.is_(None)).first()
    if not admin_user or not admin_user.password_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account not found")

    if not bcrypt.checkpw(request.password_confirmation.encode('utf-8'), admin_user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password confirmation failed")

    target_user = db.query(User).filter(User.user_id == user_id, User.deleted_at.is_(None)).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request.lock_duration_minutes is not None and request.lock_duration_minutes > 0:
        target_user.locked_until = datetime.utcnow() + timedelta(minutes=request.lock_duration_minutes)
        target_user.failed_login_attempts = 0
        message = f"Account locked for {request.lock_duration_minutes} minutes"
    else:
        target_user.locked_until = None
        target_user.failed_login_attempts = 0
        message = "Account lock removed"

    target_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(target_user)

    return {"success": True, "message": message, "data": None}

@router.delete("/users/{user_id}/hard-delete", response_model=ApiResponse)
async def hard_delete_user_account(
    user_id: str,
    request: DeleteAccountRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    load_dotenv()
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
    ALGORITHM = os.getenv("ALGORITHM", "HS256")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_role: str = payload.get("role")
        if not admin_role or not admin_role.lower() in ['system admin', 'system administrator']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only System Admins can delete accounts")
        admin_email: str = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid authentication token")

    admin_user = db.query(User).filter(User.email == admin_email, User.deleted_at.is_(None)).first()
    if not admin_user or not admin_user.password_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account not found")

    if not bcrypt.checkpw(request.password_confirmation.encode('utf-8'), admin_user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password confirmation failed")

    target_user = db.query(User).filter(User.user_id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target_user.user_id == admin_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    user_info = f"{target_user.first_name} {target_user.surname} ({target_user.email})"

    db.query(EmployeeFile).filter(EmployeeFile.user_id == user_id).delete()
    db.delete(target_user)
    db.commit()

    return {"success": True, "message": f"Account '{user_info}' permanently deleted", "data": None}

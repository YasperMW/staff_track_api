from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models.db_models import User, Role, Department, EmployeeFile, Grade
from datetime import datetime, timedelta
from timezone_config import get_current_time
from endpoints.auth_endpoints import get_current_user
import jwt
import os
from auth_config import SECRET_KEY, ALGORITHM
import logging

logger = logging.getLogger(__name__)

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

def get_email_from_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        return email
    except Exception as e:
        logger.warning("Error decoding token: %s", e)
        return None

def verify_admin_role(token: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role: str = payload.get("role")
        return user_role in ["HR", "HR Admin", "System Admin", "System Administrator", "Principal Hospital Administrator", "Head of Department", "Accountant"]
    except:
        return False

@router.get("/profile", response_model=UserProfileResponse)
async def get_current_user_profile(
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Get the profile of the currently authenticated user.
    """
    logger.info("Profile endpoint called with token: %s", token is not None)
    
    # Verify authentication
    if not token:
        logger.info("No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Extract email from token
    email = get_email_from_token(token)
    if not email:
        logger.info("Could not extract email from token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token - could not extract user information"
        )
    
    try:
        logger.info("Querying user with email: %s", email)
        # Query user by email without joins first
        user = db.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            logger.info("User not found with email: %s", email)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info("Found user: %s %s", user.first_name, user.surname)
        
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
            logger.warning("Error getting role: %s", e)
        
        try:
            if user.department_id:
                department = db.query(Department).filter(Department.department_id == user.department_id).first()
                if department:
                    department_name = department.name
                    logger.info("Found department: %s", department_name)
                else:
                    logger.info("No department found for department_id: %s", user.department_id)
            else:
                logger.info("User has no department_id")
        except Exception as e:
            logger.warning("Error getting department: %s", e)
        
        try:
            if user.designation_id:
                from models.db_models import Designation
                designation = db.query(Designation).filter(Designation.designation_id == user.designation_id).first()
                if designation:
                    designation_name = designation.name
        except Exception as e:
            logger.warning("Error getting designation: %s", e)
        
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
        logger.info("Profile response data: %s", profile_data)
        return UserProfileResponse(**profile_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Database error: %s", e)
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
    logger.info("Complete profile endpoint called with token: %s", token is not None)
    
    # Verify authentication
    if not token:
        logger.info("No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # Extract email from token
    email = get_email_from_token(token)
    if not email:
        logger.info("Could not extract email from token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token - could not extract user information"
        )
    
    try:
        logger.info("Querying complete user profile with email: %s", email)
        # Query user with all relationships
        user = db.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            logger.info("User not found with email: %s", email)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info("Found complete user: %s %s", user.first_name, user.surname)
        
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
        logger.info("Complete profile response data prepared with %d fields", len([k for k, v in profile_data.items() if v is not None]))
        return CompleteUserProfileResponse(**profile_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Database error: %s", e)
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
        user.updated_at = get_current_time()
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
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    """
    Get all users from the database with pagination.
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
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        offset = (page - 1) * page_size
        
        total_count = db.query(User).count()
        
        users = (
            db.query(User)
            .join(Role, User.role_id == Role.role_id)
            .outerjoin(Department, User.department_id == Department.department_id)
            .offset(offset)
            .limit(page_size)
            .all()
        )
        
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
            total_count=total_count
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving users: {str(e)}"
        )

@router.get("/users/active", response_model=UsersListResponse)
async def get_active_users(
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    """
    Get only active (non-deleted) users from the database with pagination.
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
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        offset = (page - 1) * page_size
        
        total_count = db.query(User).filter(User.deleted_at.is_(None)).count()
        
        users = (
            db.query(User)
            .join(Role, User.role_id == Role.role_id)
            .outerjoin(Department, User.department_id == Department.department_id)
            .filter(User.deleted_at.is_(None))
            .offset(offset)
            .limit(page_size)
            .all()
        )
        
        logger.info("Query executed successfully, found %d users", len(users))
        
        user_responses = []
        for user in users:
            try:
                # Safely access relationships
                designation_name = None
                try:
                    if user.designation:
                        designation_name = user.designation.name
                except Exception:
                    pass  # Skip designation if table doesn't have the column
                
                role_name = "Unknown"
                if user.role:
                    role_name = user.role.name
                
                department_name = None
                if user.department:
                    department_name = user.department.name
                
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
                    designation=designation_name,
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
                    role_name=role_name,
                    department_name=department_name
                )
                user_responses.append(user_data)
            except Exception as user_err:
                logger.warning("Error processing user %s: %s", user.user_id, user_err)
                continue
        
        return UsersListResponse(
            success=True,
            message=f"Successfully retrieved {len(user_responses)} active users",
            users=user_responses,
            total_count=total_count
        )
        
    except Exception as e:
        logger.warning("Error in get_active_users: %s", e)
        db.rollback()  # Rollback failed transaction
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
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role: str = payload.get("role")
        
        if not user_role or user_role.lower() not in ['system admin', 'system administrator']:
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
        user.updated_at = get_current_time()
        
        db.commit()
        db.refresh(user)
        
        # Log the role change (you might want to add an audit log table)
        logger.info("User %s %s role changed from %s to %s by System Admin", user.first_name, user.surname, old_role_name, new_role.name)
        
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
        logger.warning("Error updating user role: %s", e)
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
            detail="Only administrators can access user details"
        )

    user = db.query(User).filter(User.user_id == user_id, User.deleted_at.is_(None)).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_data = build_user_details_response(user)
    return user_data


# Update user request model
class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    surname: Optional[str] = None
    other_names: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role_id: Optional[str] = None
    department_id: Optional[str] = None
    designation_id: Optional[str] = None
    status: Optional[str] = None
    is_head_of_department: Optional[bool] = None


@router.put("/users/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Update user details.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    if not verify_admin_role(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update user details"
        )

    user = db.query(User).filter(User.user_id == user_id, User.deleted_at.is_(None)).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update only provided fields
    if request.first_name is not None:
        user.first_name = request.first_name
    if request.surname is not None:
        user.surname = request.surname
    if request.other_names is not None:
        user.other_names = request.other_names
    if request.email is not None:
        user.email = request.email
    if request.phone is not None:
        user.phone = request.phone
    if request.role_id is not None:
        user.role_id = request.role_id
    if request.department_id is not None:
        user.department_id = request.department_id
    if request.designation_id is not None:
        user.designation_id = request.designation_id
    if request.status is not None:
        user.status = request.status
    if request.is_head_of_department is not None:
        user.is_head_of_department = request.is_head_of_department
    
    user.updated_at = get_current_time()
    
    db.commit()
    db.refresh(user)
    
    return {
        "success": True,
        "message": "User updated successfully"
    }


@router.put("/users/{user_id}/lock", response_model=ApiResponse)
async def lock_user_account(
    user_id: str,
    request: LockAccountRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_role: str = payload.get("role")
        if not admin_role or admin_role.lower() not in ['system admin', 'system administrator']:
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
        target_user.locked_until = get_current_time() + timedelta(minutes=request.lock_duration_minutes)
        target_user.failed_login_attempts = 0
        message = f"Account locked for {request.lock_duration_minutes} minutes"
    else:
        target_user.locked_until = None
        target_user.failed_login_attempts = 0
        message = "Account lock removed"

    target_user.updated_at = get_current_time()
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
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_role: str = payload.get("role")
        if not admin_role or admin_role.lower() not in ['system admin', 'system administrator']:
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


class UpdateUserGradeRequest(BaseModel):
    grade_id: str


@router.put("/users/{user_id}/grade")
async def update_user_grade(
    user_id: str,
    request: UpdateUserGradeRequest,
    token: Optional[str] = Depends(get_token_from_bearer),
    db: Session = Depends(get_db)
):
    """
    Update a user's grade. Only accessible by System Admins.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role: str = payload.get("role")
        
        if not user_role or user_role.lower() not in ['system admin', 'system administrator']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only System Admins can change user grades"
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication token"
        )
    
    try:
        user = db.query(User).filter(
            User.user_id == user_id,
            User.deleted_at.is_(None)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Verify the grade exists
        grade = db.query(Grade).filter(
            Grade.grade_id == request.grade_id,
            Grade.deleted_at.is_(None)
        ).first()
        
        if not grade:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Grade not found"
            )
        
        old_grade_name = user.grade.name if user.grade else "None"
        
        user.grade_id = grade.grade_id
        user.updated_at = get_current_time()
        db.commit()
        db.refresh(user)
        
        return {
            "success": True,
            "message": f"Grade updated from '{old_grade_name}' to '{grade.name}'",
            "user_id": str(user.user_id),
            "grade_id": str(grade.grade_id),
            "grade_name": grade.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user grade: {str(e)}"
        )


@router.get("/export-data")
async def export_user_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all personal data for the current user (GDPR compliance)"""
    logger.info("Data export requested by user: %s", current_user.user_id)
    
    user_data = {
        "export_date": get_current_time().isoformat(),
        "user": {
            "user_id": str(current_user.user_id),
            "employee_number": current_user.employee_number,
            "first_name": current_user.first_name,
            "surname": current_user.surname,
            "other_names": current_user.other_names,
            "email": current_user.email,
            "phone": current_user.phone,
            "contact_number": current_user.contact_number,
            "date_of_birth": current_user.date_of_birth.isoformat() if current_user.date_of_birth else None,
            "gender": current_user.gender,
            "marital_status": current_user.marital_status,
            "spouse_name": current_user.spouse_name,
            "spouse_contact": current_user.spouse_contact,
            "home_of_origin": current_user.home_of_origin,
            "traditional_authority": current_user.traditional_authority,
            "district": current_user.district,
            "current_address": current_user.current_address,
            "designation": current_user.designation,
            "date_of_employment": current_user.date_of_employment.isoformat() if current_user.date_of_employment else None,
            "status": current_user.status,
            "selfie_verified": current_user.selfie_verified,
            "is_head_of_department": current_user.is_head_of_department,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None,
        },
        "role": {
            "role_name": current_user.role.name if current_user.role else None,
        },
        "department": {
            "department_name": current_user.department.name if current_user.department else None,
        },
        "grade": {
            "grade_name": current_user.grade.name if current_user.grade else None,
            "annual_leave_days": current_user.grade.annual_leave_days if current_user.grade else None,
        } if current_user.grade else None,
    }
    
    attendance_result = db.execute(
        text(
            """
            SELECT 
                a.attendance_id,
                a.date,
                a.check_in_time,
                a.check_out_time,
                a.status,
                a.shift_type,
                a.location_lat,
                a.location_lng,
                a.location_address,
                a.created_at
            FROM attendance a
            WHERE a.user_id = :user_id
            ORDER BY a.date DESC
            LIMIT 1000
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()
    
    user_data["attendance"] = [
        {
            "attendance_id": str(row[0]),
            "date": row[1].isoformat() if row[1] else None,
            "check_in_time": row[2].isoformat() if row[2] else None,
            "check_out_time": row[3].isoformat() if row[3] else None,
            "status": row[4],
            "shift_type": row[5],
            "location_lat": float(row[6]) if row[6] else None,
            "location_lng": float(row[7]) if row[7] else None,
            "location_address": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
        }
        for row in attendance_result
    ]
    
    leave_result = db.execute(
        text(
            """
            SELECT 
                l.leave_id,
                l.leave_type,
                l.start_date,
                l.end_date,
                l.status,
                l.reason,
                l.approved_by,
                l.approved_at,
                l.created_at
            FROM leaves l
            WHERE l.user_id = :user_id
            ORDER BY l.created_at DESC
            LIMIT 500
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()
    
    user_data["leaves"] = [
        {
            "leave_id": str(row[0]),
            "leave_type": row[1],
            "start_date": row[2].isoformat() if row[2] else None,
            "end_date": row[3].isoformat() if row[3] else None,
            "status": row[4],
            "reason": row[5],
            "approved_by": str(row[6]) if row[6] else None,
            "approved_at": row[7].isoformat() if row[7] else None,
            "created_at": row[8].isoformat() if row[8] else None,
        }
        for row in leave_result
    ]
    
    requests_result = db.execute(
        text(
            """
            SELECT 
                r.request_id,
                r.type,
                r.start_date,
                r.end_date,
                r.status,
                r.approval_level,
                r.leave_grant_required,
                r.contact_address,
                r.reason_for_leaving,
                r.travel_date,
                r.travel_place,
                r.created_at
            FROM requests r
            WHERE r.user_id = :user_id
              AND r.deleted_at IS NULL
            ORDER BY r.created_at DESC
            LIMIT 500
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()
    
    user_data["requests"] = [
        {
            "request_id": str(row[0]),
            "type": row[1],
            "start_date": row[2].isoformat() if row[2] else None,
            "end_date": row[3].isoformat() if row[3] else None,
            "status": row[4],
            "approval_level": row[5],
            "leave_grant_required": row[6],
            "contact_address": row[7],
            "reason_for_leaving": row[8],
            "travel_date": row[9].isoformat() if row[9] else None,
            "travel_place": row[10],
            "created_at": row[11].isoformat() if row[11] else None,
        }
        for row in requests_result
    ]
    
    notifications_result = db.execute(
        text(
            """
            SELECT 
                n.notification_id,
                n.title,
                n.message,
                n.notification_type,
                n.is_read,
                n.created_at
            FROM notifications n
            WHERE n.user_id = :user_id
            ORDER BY n.created_at DESC
            LIMIT 500
            """
        ),
        {"user_id": current_user.user_id},
    ).fetchall()
    
    user_data["notifications"] = [
        {
            "notification_id": str(row[0]),
            "title": row[1],
            "message": row[2],
            "notification_type": row[3],
            "is_read": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
        for row in notifications_result
    ]
    
    logger.info("Data export completed for user: %s", current_user.user_id)
    
    return user_data

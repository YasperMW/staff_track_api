from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import time

from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, ShiftConfiguration
from timezone_config import get_current_time

router = APIRouter(prefix="/shift-configurations", tags=["shift-configurations"])

# Pydantic models for request/response
class ShiftConfigurationResponse(BaseModel):
    shift_config_id: str
    shift_name: str
    shift_type: str
    check_in_earliest: str
    check_in_latest: str
    official_start_time: str
    check_out_earliest: str
    check_out_latest: str
    official_end_time: str
    extended_start_time: str
    late_threshold: str
    is_active: bool
    description: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

class ShiftConfigurationCreate(BaseModel):
    shift_name: str
    shift_type: str
    check_in_earliest: str
    check_in_latest: str
    official_start_time: str
    check_out_earliest: str
    check_out_latest: str
    official_end_time: str
    extended_start_time: str
    late_threshold: str
    description: Optional[str] = None

class ShiftConfigurationUpdate(BaseModel):
    shift_name: Optional[str] = None
    check_in_earliest: Optional[str] = None
    check_in_latest: Optional[str] = None
    official_start_time: Optional[str] = None
    check_out_earliest: Optional[str] = None
    check_out_latest: Optional[str] = None
    official_end_time: Optional[str] = None
    extended_start_time: Optional[str] = None
    late_threshold: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None

def parse_time_string(time_str: str) -> time:
    """Parse time string in HH:MM format to time object"""
    try:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid time format: {time_str}. Use HH:MM format."
        )

def format_time_for_response(time_obj: time) -> str:
    """Format time object to HH:MM string"""
    return time_obj.strftime('%H:%M')

@router.get("/", response_model=List[ShiftConfigurationResponse])
async def get_shift_configurations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_only: bool = True
):
    """
    Get all shift configurations
    Only accessible to HR Admin and System Admin roles
    """
    # Check permissions
    if current_user.role.name not in ['HR', 'System Admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR Admin and System Admin can view shift configurations"
        )
    
    query = db.query(ShiftConfiguration)
    
    if active_only:
        query = query.filter(ShiftConfiguration.is_active == True)
    
    configurations = query.order_by(ShiftConfiguration.shift_type).all()
    
    return [
        ShiftConfigurationResponse(
            shift_config_id=str(config.shift_config_id),
            shift_name=config.shift_name,
            shift_type=config.shift_type,
            check_in_earliest=format_time_for_response(config.check_in_earliest),
            check_in_latest=format_time_for_response(config.check_in_latest),
            official_start_time=format_time_for_response(config.official_start_time),
            check_out_earliest=format_time_for_response(config.check_out_earliest),
            check_out_latest=format_time_for_response(config.check_out_latest),
            official_end_time=format_time_for_response(config.official_end_time),
            extended_start_time=format_time_for_response(config.extended_start_time),
            late_threshold=format_time_for_response(config.late_threshold),
            is_active=config.is_active,
            description=config.description,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat()
        )
        for config in configurations
    ]

@router.get("/{shift_type}", response_model=ShiftConfigurationResponse)
async def get_shift_configuration(
    shift_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific shift configuration by type
    """
    # Check permissions
    if current_user.role.name not in ['HR', 'System Admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR Admin and System Admin can view shift configurations"
        )
    
    config = db.query(ShiftConfiguration).filter(
        and_(
            ShiftConfiguration.shift_type == shift_type,
            ShiftConfiguration.is_active == True
        )
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift configuration for '{shift_type}' not found"
        )
    
    return ShiftConfigurationResponse(
        shift_config_id=str(config.shift_config_id),
        shift_name=config.shift_name,
        shift_type=config.shift_type,
        check_in_earliest=format_time_for_response(config.check_in_earliest),
        check_in_latest=format_time_for_response(config.check_in_latest),
        official_start_time=format_time_for_response(config.official_start_time),
        check_out_earliest=format_time_for_response(config.check_out_earliest),
        check_out_latest=format_time_for_response(config.check_out_latest),
        official_end_time=format_time_for_response(config.official_end_time),
        extended_start_time=format_time_for_response(config.extended_start_time),
        late_threshold=format_time_for_response(config.late_threshold),
        is_active=config.is_active,
        description=config.description,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat()
    )

@router.post("/", response_model=ShiftConfigurationResponse)
async def create_shift_configuration(
    config_data: ShiftConfigurationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new shift configuration
    Only accessible to HR Admin and System Admin roles
    """
    # Check permissions
    if current_user.role.name not in ['HR', 'System Admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR Admin and System Admin can view shift configurations"
        )
    
    # Check if shift type already exists
    existing = db.query(ShiftConfiguration).filter(
        ShiftConfiguration.shift_type == config_data.shift_type
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Shift configuration for '{config_data.shift_type}' already exists"
        )
    
    # Create new configuration
    new_config = ShiftConfiguration(
        shift_name=config_data.shift_name,
        shift_type=config_data.shift_type,
        check_in_earliest=parse_time_string(config_data.check_in_earliest),
        check_in_latest=parse_time_string(config_data.check_in_latest),
        official_start_time=parse_time_string(config_data.official_start_time),
        check_out_earliest=parse_time_string(config_data.check_out_earliest),
        check_out_latest=parse_time_string(config_data.check_out_latest),
        official_end_time=parse_time_string(config_data.official_end_time),
        extended_start_time=parse_time_string(config_data.extended_start_time),
        late_threshold=parse_time_string(config_data.late_threshold),
        description=config_data.description,
        created_by=current_user.user_id,
        updated_by=current_user.user_id
    )
    
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    
    return ShiftConfigurationResponse(
        shift_config_id=str(new_config.shift_config_id),
        shift_name=new_config.shift_name,
        shift_type=new_config.shift_type,
        check_in_earliest=format_time_for_response(new_config.check_in_earliest),
        check_in_latest=format_time_for_response(new_config.check_in_latest),
        official_start_time=format_time_for_response(new_config.official_start_time),
        check_out_earliest=format_time_for_response(new_config.check_out_earliest),
        check_out_latest=format_time_for_response(new_config.check_out_latest),
        official_end_time=format_time_for_response(new_config.official_end_time),
        extended_start_time=format_time_for_response(new_config.extended_start_time),
        late_threshold=format_time_for_response(new_config.late_threshold),
        is_active=new_config.is_active,
        description=new_config.description,
        created_at=new_config.created_at.isoformat(),
        updated_at=new_config.updated_at.isoformat()
    )

@router.put("/{shift_config_id}", response_model=ShiftConfigurationResponse)
async def update_shift_configuration(
    shift_config_id: str,
    config_data: ShiftConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing shift configuration
    Only accessible to HR Admin and System Admin roles
    """
    # Check permissions
    if current_user.role.name not in ['HR', 'System Admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR Admin and System Admin can create shift configurations"
        )
    
    config = db.query(ShiftConfiguration).filter(
        ShiftConfiguration.shift_config_id == shift_config_id
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift configuration not found"
        )
    
    # Update fields
    update_data = config_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field in ['check_in_earliest', 'check_in_latest', 'official_start_time', 
                    'check_out_earliest', 'check_out_latest', 'official_end_time',
                    'extended_start_time', 'late_threshold'] and value is not None:
            setattr(config, field, parse_time_string(value))
        elif value is not None:
            setattr(config, field, value)
    
    config.updated_by = current_user.user_id
    db.commit()
    db.refresh(config)
    
    return ShiftConfigurationResponse(
        shift_config_id=str(config.shift_config_id),
        shift_name=config.shift_name,
        shift_type=config.shift_type,
        check_in_earliest=format_time_for_response(config.check_in_earliest),
        check_in_latest=format_time_for_response(config.check_in_latest),
        official_start_time=format_time_for_response(config.official_start_time),
        check_out_earliest=format_time_for_response(config.check_out_earliest),
        check_out_latest=format_time_for_response(config.check_out_latest),
        official_end_time=format_time_for_response(config.official_end_time),
        extended_start_time=format_time_for_response(config.extended_start_time),
        late_threshold=format_time_for_response(config.late_threshold),
        is_active=config.is_active,
        description=config.description,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat()
    )

@router.delete("/{shift_config_id}")
async def delete_shift_configuration(
    shift_config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete a shift configuration
    Only accessible to HR Admin and System Admin roles
    """
    # Check permissions
    if current_user.role.name not in ['HR', 'System Admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR Admin and System Admin can update shift configurations"
        )
    
    config = db.query(ShiftConfiguration).filter(
        ShiftConfiguration.shift_config_id == shift_config_id
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift configuration not found"
        )
    
    # Soft delete by setting is_active to False
    config.is_active = False
    config.updated_by = current_user.user_id
    db.commit()
    
    return {"message": "Shift configuration deleted successfully"}

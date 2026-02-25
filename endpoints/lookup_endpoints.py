from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models.db_models import Role, Department

router = APIRouter()

# Pydantic models for response
class RoleResponse(BaseModel):
    role_id: str
    name: str
    created_at: str

    class Config:
        from_attributes = True

class DepartmentResponse(BaseModel):
    department_id: str
    name: str
    description: Optional[str]
    created_at: str
    designations: List[str]

    class Config:
        from_attributes = True

class RolesListResponse(BaseModel):
    success: bool
    message: str
    roles: List[RoleResponse]
    total_count: int

class DepartmentsListResponse(BaseModel):
    success: bool
    message: str
    departments: List[DepartmentResponse]
    total_count: int

# Department designations mapping
DEPARTMENT_DESIGNATIONS = {
    'Emergency Department': [
        'Emergency Medicine Physician', 'Emergency Nurse', 'Paramedic', 
        'Emergency Medical Technician', 'Triage Nurse', 'Emergency Department Manager'
    ],
    'Intensive Care Unit (ICU)': [
        'Intensivist', 'ICU Nurse', 'Critical Care Nurse', 'Respiratory Therapist',
        'ICU Manager', 'Critical Care Physician'
    ],
    'Operating Room (OR)': [
        'Surgeon', 'Anesthesiologist', 'OR Nurse', 'Surgical Technologist',
        'OR Manager', 'Perioperative Nurse'
    ],
    'Medical-Surgical Unit': [
        'Staff Nurse', 'Charge Nurse', 'Medical-Surgical Nurse', 'Patient Care Technician',
        'Unit Manager', 'Clinical Nurse Leader'
    ],
    'Obstetrics and Gynecology (OB/GYN)': [
        'Obstetrician', 'Gynecologist', 'OB/GYN Nurse', 'Midwife',
        'Labor and Delivery Nurse', 'OB/GYN Physician Assistant'
    ],
    'Pediatrics': [
        'Pediatrician', 'Pediatric Nurse', 'Pediatric Nurse Practitioner',
        'Child Life Specialist', 'Pediatric Medical Assistant'
    ],
    'Radiology': [
        'Radiologist', 'Radiology Technician', 'X-ray Technician',
        'MRI Technician', 'CT Technician', 'Ultrasound Technician'
    ],
    'Laboratory': [
        'Lab Technician', 'Lab Manager', 'Medical Technologist',
        'Lab Scientist', 'Phlebotomist', 'Quality Assurance Officer'
    ],
    'Pharmacy': [
        'Pharmacist', 'Pharmacy Technician', 'Pharmacy Manager',
        'Clinical Pharmacist', 'Dispensing Technician', 'Inventory Officer'
    ],
    'Physical Therapy': [
        'Physical Therapist', 'Physical Therapy Assistant', 'Rehabilitation Manager',
        'Sports Medicine Specialist', 'Occupational Therapist'
    ],
    'Administration': [
        'Hospital Administrator', 'Administrative Officer', 'Executive Assistant',
        'Office Manager', 'Administrative Secretary', 'Records Officer'
    ],
    'Finance': [
        'Accountant', 'Financial Controller', 'Billing Officer',
        'Finance Manager', 'Payroll Officer', 'Accounts Clerk'
    ],
    'Human Resources': [
        'HR Manager', 'HR Officer', 'Recruitment Officer',
        'Training Officer', 'HR Assistant', 'Compensation Specialist'
    ],
    'Information Technology (IT)': [
        'IT Manager', 'System Administrator', 'Network Administrator',
        'Database Administrator', 'Software Developer', 'IT Support Technician'
    ],
    'Marketing and Communications': [
        'Marketing Manager', 'Communications Director', 'Public Relations Officer',
        'Content Creator', 'Social Media Manager', 'Brand Manager'
    ]
}

@router.get("/roles", response_model=RolesListResponse)
async def get_all_roles(db: Session = Depends(get_db)):
    """
    Get all available roles from the database.
    """
    try:
        # Simple query without relationships
        roles = db.execute(text("SELECT role_id, name, created_at FROM roles WHERE deleted_at IS NULL")).fetchall()
        
        role_responses = []
        for role in roles:
            role_data = RoleResponse(
                role_id=str(role[0]),
                name=role[1],
                created_at=role[2].isoformat() if role[2] else None
            )
            role_responses.append(role_data)
        
        return RolesListResponse(
            success=True,
            message=f"Successfully retrieved {len(role_responses)} roles",
            roles=role_responses,
            total_count=len(role_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving roles: {str(e)}"
        )

@router.get("/departments", response_model=DepartmentsListResponse)
async def get_all_departments(db: Session = Depends(get_db)):
    """
    Get all available departments with their designations from the database.
    """
    try:
        # Simple query without relationships
        departments = db.execute(text("SELECT department_id, name, description, created_at FROM departments WHERE deleted_at IS NULL")).fetchall()
        
        department_responses = []
        for dept in departments:
            # Get designations for this department from mapping
            designations = DEPARTMENT_DESIGNATIONS.get(dept[1], [])
            
            dept_data = DepartmentResponse(
                department_id=str(dept[0]),
                name=dept[1],
                description=dept[2],
                created_at=dept[3].isoformat() if dept[3] else None,
                designations=designations
            )
            department_responses.append(dept_data)
        
        return DepartmentsListResponse(
            success=True,
            message=f"Successfully retrieved {len(department_responses)} departments",
            departments=department_responses,
            total_count=len(department_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving departments: {str(e)}"
        )

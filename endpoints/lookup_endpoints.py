from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from database import get_db
from models.db_models import Role, Department, Designation
from datetime import datetime
import uuid

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

class DesignationResponse(BaseModel):
    designation_id: str
    name: str
    description: Optional[str]
    department_id: str
    department_name: Optional[str]
    created_at: str

    class Config:
        from_attributes = True

# Request models for CRUD operations
class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)

class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)

class DesignationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    department_id: str

class DesignationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    department_id: Optional[str] = None

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
        departments = db.execute(text("SELECT department_id, name, description, created_at FROM departments WHERE deleted_at IS NULL")).fetchall()

        department_responses = []
        for dept in departments:
            # Get designations for this department from the database
            designations_result = db.execute(
                text("SELECT name FROM designations WHERE department_id = :department_id AND deleted_at IS NULL ORDER BY name"),
                {"department_id": dept[0]}
            ).fetchall()
            designations = [d[0] for d in designations_result]

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

@router.post("/departments", response_model=dict)
async def create_department(department_data: DepartmentCreate, db: Session = Depends(get_db)):
    """
    Create a new department.
    """
    try:
        # Check if department name already exists
        existing = db.execute(
            text("SELECT department_id FROM departments WHERE name = :name AND deleted_at IS NULL"),
            {"name": department_data.name}
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department with this name already exists"
            )
        
        # Create new department
        department_id = uuid.uuid4()
        now = datetime.now()
        
        db.execute(
            text("""
                INSERT INTO departments (department_id, name, description, created_at, updated_at)
                VALUES (:department_id, :name, :description, :created_at, :updated_at)
            """),
            {
                "department_id": department_id,
                "name": department_data.name,
                "description": department_data.description,
                "created_at": now,
                "updated_at": now
            }
        )
        db.commit()
        
        return {
            "success": True,
            "message": "Department created successfully",
            "department_id": str(department_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating department: {str(e)}"
        )

@router.put("/departments/{department_id}", response_model=dict)
async def update_department(department_id: str, department_data: DepartmentUpdate, db: Session = Depends(get_db)):
    """
    Update an existing department.
    """
    try:
        # Check if department exists
        existing = db.execute(
            text("SELECT department_id FROM departments WHERE department_id = :department_id AND deleted_at IS NULL"),
            {"department_id": department_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )
        
        # Check if new name conflicts with existing department
        if department_data.name:
            name_check = db.execute(
                text("""
                    SELECT department_id FROM departments 
                    WHERE name = :name AND department_id != :department_id AND deleted_at IS NULL
                """),
                {"name": department_data.name, "department_id": department_id}
            ).fetchone()
            
            if name_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department with this name already exists"
                )
        
        # Build update query dynamically
        update_fields = []
        update_values = {"department_id": department_id, "updated_at": datetime.now()}
        
        if department_data.name is not None:
            update_fields.append("name = :name")
            update_values["name"] = department_data.name
        
        if department_data.description is not None:
            update_fields.append("description = :description")
            update_values["description"] = department_data.description
        
        if update_fields:
            query = f"""
                UPDATE departments 
                SET {', '.join(update_fields)}, updated_at = :updated_at
                WHERE department_id = :department_id
            """
            db.execute(text(query), update_values)
            db.commit()
        
        return {
            "success": True,
            "message": "Department updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating department: {str(e)}"
        )

@router.delete("/departments/{department_id}", response_model=dict)
async def delete_department(department_id: str, db: Session = Depends(get_db)):
    """
    Soft delete a department.
    """
    try:
        # Check if department exists
        existing = db.execute(
            text("""
                SELECT department_id FROM departments 
                WHERE department_id = :department_id AND deleted_at IS NULL
            """),
            {"department_id": department_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )
        
        # Check if department has users
        users_count = db.execute(
            text("""
                SELECT COUNT(*) FROM users 
                WHERE department_id = :department_id AND deleted_at IS NULL
            """),
            {"department_id": department_id}
        ).scalar()
        
        if users_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete department with associated users"
            )
        
        # Soft delete the department
        db.execute(
            text("""
                UPDATE departments 
                SET deleted_at = :deleted_at, updated_at = :updated_at
                WHERE department_id = :department_id
            """),
            {
                "department_id": department_id,
                "deleted_at": datetime.now(),
                "updated_at": datetime.now()
            }
        )
        db.commit()
        
        return {
            "success": True,
            "message": "Department deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting department: {str(e)}"
        )

# Designation endpoints
@router.get("/designations", response_model=dict)
async def get_all_designations(db: Session = Depends(get_db)):
    """
    Get all available designations from the database.
    """
    try:
        # Query using SQLAlchemy ORM instead of raw SQL
        designations_query = db.query(Designation, Department.name.label('department_name')).join(
            Department, Designation.department_id == Department.department_id
        ).filter(Designation.deleted_at.is_(None)).order_by(Department.name, Designation.name)
        
        designation_responses = []
        for designation, department_name in designations_query:
            designation_data = DesignationResponse(
                designation_id=str(designation.designation_id),
                name=designation.name,
                description=designation.description,
                department_id=str(designation.department_id) if designation.department_id else None,
                department_name=department_name,
                created_at=designation.created_at.isoformat() if designation.created_at else None
            )
            designation_responses.append(designation_data)
        
        return {
            "success": True,
            "message": f"Successfully retrieved {len(designation_responses)} designations",
            "designations": designation_responses,
            "total_count": len(designation_responses)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving designations: {str(e)}"
        )

@router.post("/designations", response_model=dict)
async def create_designation(designation_data: DesignationCreate, db: Session = Depends(get_db)):
    """
    Create a new designation.
    """
    try:
        # Check if department exists
        department_exists = db.execute(
            text("SELECT department_id FROM departments WHERE department_id = :department_id AND deleted_at IS NULL"),
            {"department_id": designation_data.department_id}
        ).fetchone()
        
        if not department_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department not found"
            )
        
        # Check if designation name already exists in the same department
        existing = db.execute(
            text("""
                SELECT designation_id FROM designations 
                WHERE name = :name AND department_id = :department_id AND deleted_at IS NULL
            """),
            {"name": designation_data.name, "department_id": designation_data.department_id}
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Designation with this name already exists in this department"
            )
        
        # Create new designation
        designation_id = uuid.uuid4()
        now = datetime.now()
        
        db.execute(
            text("""
                INSERT INTO designations (designation_id, name, description, department_id, created_at, updated_at)
                VALUES (:designation_id, :name, :description, :department_id, :created_at, :updated_at)
            """),
            {
                "designation_id": designation_id,
                "name": designation_data.name,
                "description": designation_data.description,
                "department_id": designation_data.department_id,
                "created_at": now,
                "updated_at": now
            }
        )
        db.commit()
        
        return {
            "success": True,
            "message": "Designation created successfully",
            "designation_id": str(designation_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating designation: {str(e)}"
        )

@router.put("/designations/{designation_id}", response_model=dict)
async def update_designation(designation_id: str, designation_data: DesignationUpdate, db: Session = Depends(get_db)):
    """
    Update an existing designation.
    """
    try:
        # Check if designation exists
        existing = db.execute(
            text("SELECT department_id FROM designations WHERE designation_id = :designation_id AND deleted_at IS NULL"),
            {"designation_id": designation_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Designation not found"
            )
        
        # If updating department, check if it exists
        new_department_id = designation_data.department_id or existing[0]
        if designation_data.department_id and designation_data.department_id != existing[0]:
            department_exists = db.execute(
                text("SELECT department_id FROM departments WHERE department_id = :department_id AND deleted_at IS NULL"),
                {"department_id": designation_data.department_id}
            ).fetchone()
            
            if not department_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department not found"
                )
        
        # Check if new name conflicts with existing designation in the same department
        if designation_data.name:
            name_check = db.execute(
                text("""
                    SELECT designation_id FROM designations 
                    WHERE name = :name AND department_id = :department_id 
                    AND designation_id != :designation_id AND deleted_at IS NULL
                """),
                {
                    "name": designation_data.name, 
                    "department_id": new_department_id,
                    "designation_id": designation_id
                }
            ).fetchone()
            
            if name_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Designation with this name already exists in this department"
                )
        
        # Build update query dynamically
        update_fields = []
        update_values = {"designation_id": designation_id, "updated_at": datetime.now()}
        
        if designation_data.name is not None:
            update_fields.append("name = :name")
            update_values["name"] = designation_data.name
        
        if designation_data.description is not None:
            update_fields.append("description = :description")
            update_values["description"] = designation_data.description
        
        if designation_data.department_id is not None:
            update_fields.append("department_id = :department_id")
            update_values["department_id"] = designation_data.department_id
        
        if update_fields:
            query = f"""
                UPDATE designations 
                SET {', '.join(update_fields)}, updated_at = :updated_at
                WHERE designation_id = :designation_id
            """
            db.execute(text(query), update_values)
            db.commit()
        
        return {
            "success": True,
            "message": "Designation updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating designation: {str(e)}"
        )

@router.delete("/designations/{designation_id}", response_model=dict)
async def delete_designation(designation_id: str, db: Session = Depends(get_db)):
    """
    Soft delete a designation.
    """
    try:
        # Check if designation exists
        existing = db.execute(
            text("""
                SELECT designation_id FROM designations 
                WHERE designation_id = :designation_id AND deleted_at IS NULL
            """),
            {"designation_id": designation_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Designation not found"
            )
        
        # Check if designation has users
        users_count = db.execute(
            text("""
                SELECT COUNT(*) FROM users 
                WHERE designation_id = :designation_id AND deleted_at IS NULL
            """),
            {"designation_id": designation_id}
        ).scalar()
        
        if users_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete designation with associated users"
            )
        
        # Soft delete the designation
        db.execute(
            text("""
                UPDATE designations 
                SET deleted_at = :deleted_at, updated_at = :updated_at
                WHERE designation_id = :designation_id
            """),
            {
                "designation_id": designation_id,
                "deleted_at": datetime.now(),
                "updated_at": datetime.now()
            }
        )
        db.commit()
        
        return {
            "success": True,
            "message": "Designation deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting designation: {str(e)}"
        )

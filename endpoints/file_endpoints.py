from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
import os
import uuid
import aiofiles
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db
from endpoints.auth_endpoints import get_current_user
from models.db_models import User, EmployeeFile
from timezone_config import get_current_time

router = APIRouter()

# Create uploads directory if it doesn't exist
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/profile_photos", exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/employee_files", exist_ok=True)

@router.post("/upload/profile-photo")
async def upload_profile_photo(file: UploadFile = File(...)):
    try:
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="File must be an image"
            )
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, "profile_photos", unique_filename)
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        file_url = f"profile_photos/{unique_filename}"
        return JSONResponse({
            "success": True,
            "message": "Profile photo uploaded successfully",
            "file_url": file_url,
            "filename": unique_filename
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading file: {str(e)}"
        )

@router.get("/uploads/profile_photos/{filename}")
async def get_profile_photo(filename: str):
    file_path = os.path.join(UPLOAD_DIR, "profile_photos", filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(file_path)

@router.get("/profile_photos/{filename}")
async def get_profile_photo_v2(filename: str):
    """Serve profile photos - new path without /uploads prefix"""
    file_path = os.path.join(UPLOAD_DIR, "profile_photos", filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(file_path)

@router.get("/employee_files/{filename}")
async def get_employee_file(filename: str):
    """Serve employee files"""
    file_path = os.path.join(UPLOAD_DIR, "employee_files", filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(file_path)

@router.post("/upload/employee-file")
async def upload_employee_file(
    file: UploadFile = File(...),
    file_type: str = "payslip",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        allowed_ext = os.getenv("ALLOWED_UPLOAD_EXT", "pdf,doc,docx,jpg,jpeg,png").split(",")
        allowed_ext = [e.strip().lower() for e in allowed_ext if e.strip()]
        max_mb = float(os.getenv("MAX_UPLOAD_MB", "10"))
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else 'dat'
        if file_extension not in allowed_ext:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, "employee_files", unique_filename)
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            size_mb = (len(content) / (1024 * 1024))
            if size_mb > max_mb:
                raise HTTPException(status_code=400, detail="File too large")
            await f.write(content)
        file_url = f"employee_files/{unique_filename}"
        rec = EmployeeFile(user_id=current_user.user_id, file_type=file_type, file_url=file_url, upload_date=get_current_time())
        db.add(rec)
        db.commit()
        return {"success": True, "file_url": file_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/employee-files")
async def list_employee_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(EmployeeFile).filter(EmployeeFile.user_id == current_user.user_id).order_by(EmployeeFile.upload_date.desc()).all()
    return [{"file_id": str(r.employee_file_id), "file_type": r.file_type, "file_url": r.file_url, "upload_date": r.upload_date.isoformat() if r.upload_date else None} for r in rows]

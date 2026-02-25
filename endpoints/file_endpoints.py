from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import os
import uuid
import aiofiles
from datetime import datetime

router = APIRouter()

# Create uploads directory if it doesn't exist
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/profile_photos", exist_ok=True)

@router.post("/upload/profile-photo")
async def upload_profile_photo(file: UploadFile = File(...)):
    try:
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="File must be an image"
            )
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, "profile_photos", unique_filename)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Generate URL (in production, this would be your actual domain)
        file_url = f"http://127.0.0.1:8000/uploads/profile_photos/{unique_filename}"
        
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

import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path

from app.config import settings

router = APIRouter(prefix="/media", tags=["media"])

@router.post("/upload")
async def upload_media(file: UploadFile = File(...)):
    """
    Upload media file (image or video)
    Returns the path to the uploaded file
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Ensure upload directory exists
    upload_dir = Path(settings.UPLOADS_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate safe filename
    ext = file.filename.split(".")[-1].lower()
    allowed_extensions = ['mp4', 'mov', 'avi', 'jpg', 'jpeg', 'png', 'gif', 'webp']
    
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not allowed")
    
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = upload_dir / filename

    # Save file
    content = await file.read()
    file_path.write_bytes(content)

    # Return the public URL path (what the frontend will use)
    return {
        "filename": filename,
        "path": f"/media/uploads/{filename}",  # Full URL path for frontend
        "original_name": file.filename,
        "size": len(content)
    }
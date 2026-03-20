import os
import uuid
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.storage import upload_file

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/upload")
async def upload_media(file: UploadFile = File(...)):
    """
    Upload media file (image or video) to cloud storage.
    Returns the public URL — the file is NOT kept on disk.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = file.filename.split(".")[-1].lower()
    allowed_extensions = ["mp4", "mov", "avi", "jpg", "jpeg", "png", "gif", "webp"]

    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not allowed")

    content = await file.read()
    size = len(content)

    # Write to a temp file so boto3 can read it
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        remote_key = f"uploads/{uuid.uuid4()}.{ext}"
        public_url = upload_file(tmp_path, remote_key)
    finally:
        os.unlink(tmp_path)

    return {
        "url": public_url,
        "original_name": file.filename,
        "size": size,
    }

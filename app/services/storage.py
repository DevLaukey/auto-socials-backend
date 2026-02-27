"""
Cloud Storage Service (Tigris / S3-compatible)

Handles uploading and deleting files from object storage.
Only the public URL is stored in the database.
"""

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_ENDPOINT_URL_S3,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def upload_file(local_path: str, remote_key: str) -> str:
    """
    Upload a local file to cloud storage.

    Args:
        local_path: Absolute path to the local file.
        remote_key: Key (path) inside the bucket, e.g. "clips/uuid.mp4".

    Returns:
        Public URL of the uploaded file.
    """
    client = _get_client()
    bucket = settings.BUCKET_NAME

    try:
        client.upload_file(
            local_path,
            bucket,
            remote_key,
            ExtraArgs={"ContentType": _content_type(local_path)},
        )
        logger.info(f"[Storage] Uploaded {local_path} → {remote_key}")
    except ClientError as e:
        logger.error(f"[Storage] Upload failed: {e}")
        raise RuntimeError(f"Storage upload failed: {e}") from e

    # Build public URL
    if settings.BUCKET_PUBLIC_URL:
        base = settings.BUCKET_PUBLIC_URL.rstrip("/")
        return f"{base}/{remote_key}"

    # Fallback: standard S3-style URL via endpoint
    endpoint = settings.AWS_ENDPOINT_URL_S3.rstrip("/")
    return f"{endpoint}/{bucket}/{remote_key}"


def delete_file(remote_key: str) -> None:
    """Delete a file from cloud storage. Silently ignores missing keys."""
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.BUCKET_NAME, Key=remote_key)
        logger.info(f"[Storage] Deleted {remote_key}")
    except ClientError as e:
        logger.warning(f"[Storage] Delete failed for {remote_key}: {e}")


def _content_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return types.get(ext, "application/octet-stream")

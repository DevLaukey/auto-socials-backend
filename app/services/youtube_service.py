"""
YouTube posting service.

LOGIC:
- Upload video to YouTube
- Apply metadata
- Use OAuth credentials
- NO database mutations here
"""

import logging
from typing import Union

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class YouTubeService:
    def __init__(self, credentials: Union[Credentials, dict]):
        """
        Accepts EITHER:
        - google.oauth2.credentials.Credentials (preferred, current)
        - legacy credentials dict (backward compatibility)

        Dict format (legacy):
        - access_token
        - refresh_token
        - client_id
        - client_secret
        """

        # ✅ NEW PATH (correct, used by Celery + FastAPI)
        if isinstance(credentials, Credentials):
            self.credentials = credentials

        # ✅ LEGACY PATH (do NOT remove — backward compatibility)
        elif isinstance(credentials, dict):
            self.credentials = Credentials(
                token=credentials.get("access_token"),
                refresh_token=credentials.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=credentials.get("client_id"),
                client_secret=credentials.get("client_secret"),
            )

        else:
            raise TypeError(
                "YouTubeService credentials must be a Credentials object or dict"
            )

        self.youtube = build(
            "youtube",
            "v3",
            credentials=self.credentials,
            cache_discovery=False,
        )

    def upload_video(
        self,
        video_file: str,
        title: str,
        description: str,
        tags=None,
        privacy_status="public",
    ):
        """
        Upload a video to YouTube.

        Raises exception on failure.
        """

        logger.info(f"Uploading video to YouTube: {video_file}")

        request = self.youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags or [],
                },
                "status": {
                    "privacyStatus": privacy_status,
                },
            },
            media_body=MediaFileUpload(
                video_file,
                chunksize=-1,
                resumable=True,
            ),
        )

        response = request.execute()
        video_id = response.get("id")

        if not video_id:
            raise RuntimeError("YouTube upload succeeded but no video ID returned")

        logger.info(f"YouTube upload successful | video_id={video_id}")

        return {
            "video_id": video_id,
            "raw_response": response,
        }


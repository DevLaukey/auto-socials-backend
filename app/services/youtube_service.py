"""
YouTube posting service.

LOGIC:
- Upload video to YouTube
- Apply metadata
- Use OAuth credentials
- NO database mutations here
"""

import logging
import re
from typing import Union

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
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

    def post_comment(self, video_url: str, comment: str) -> dict:
        """
        Post a top-level comment on a YouTube video.

        Accepts full YouTube URLs or bare video IDs.
        """
        video_id = self._extract_video_id(video_url)

        try:
            response = self.youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment,
                            }
                        },
                    }
                },
            ).execute()

            comment_id = response.get("id")
            logger.info(f"YouTube comment posted | comment_id={comment_id} video_id={video_id}")
            return {"comment_id": comment_id, "raw_response": response}

        except HttpError as e:
            logger.error(f"YouTube API error posting comment: {e}")
            raise

    @staticmethod
    def _extract_video_id(url: str) -> str:
        """Extract video ID from a YouTube URL, or return the value as-is if already an ID."""
        patterns = [
            r"(?:youtube\.com/watch\?v=)([\w-]+)",
            r"(?:youtu\.be/)([\w-]+)",
            r"(?:youtube\.com/embed/)([\w-]+)",
            r"(?:youtube\.com/v/)([\w-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return url  # assume it's already a bare video ID


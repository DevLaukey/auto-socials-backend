from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import time

from app.services.database import (
    get_youtube_posts_with_tokens,
    update_post_engagement,
    update_youtube_tokens,
)


def refresh_token_if_needed(account):
    creds = Credentials(
        token=account["access_token"],
        refresh_token=account["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=None,   # Will be auto-read from client_secret
        client_secret=None,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        update_youtube_tokens(
            account_id=None,  # We’ll fix this below if needed
            access_token=creds.token,
            expires_at=int(time.time()) + 3600,
        )

    return creds


def fetch_and_update_youtube_stats():
    posts = get_youtube_posts_with_tokens()

    for post in posts:
        try:
            creds = Credentials(
                token=post["access_token"],
                refresh_token=post["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
            )

            youtube = build("youtube", "v3", credentials=creds)

            response = youtube.videos().list(
                part="statistics",
                id=post["video_id"]
            ).execute()

            if not response["items"]:
                continue

            stats = response["items"][0]["statistics"]

            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            views = int(stats.get("viewCount", 0))

            update_post_engagement(
                post_id=post["post_id"],
                likes=likes,
                comments=comments,
                views=views,
            )

        except Exception as e:
            print(f"Failed to update stats for post {post['post_id']}: {e}")

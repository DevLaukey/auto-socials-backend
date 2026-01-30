from instagrapi import Client
from instagrapi.exceptions import LoginRequired
from app.services.database import (
    get_instagram_credentials,
    update_instagram_session,
)
import os


class InstagramService:
    def __init__(self, account_id: int):
        self.account_id = account_id
        self.client = Client()

    # -------------------------
    # Authentication
    # -------------------------

    def login(self, force: bool = False):
        creds = get_instagram_credentials(self.account_id)
        if not creds:
            raise ValueError("Instagram credentials not found")

        username = creds["username"]
        password = creds["password"]
        session = creds.get("session")

        if session and not force:
            try:
                self.client.set_settings(session)
                self.client.login(username, password)
                return
            except Exception:
                pass  # fall through to full login

        # FULL LOGIN
        self.client = Client()
        self.client.login(username, password)

        update_instagram_session(
            self.account_id,
            self.client.get_settings()
        )

    # -------------------------
    # Feed post
    # -------------------------

    def post_feed(
        self,
        media_path: str,
        caption: str = "",
        location: str = None,
        disable_comments: bool = False,
    ):
        self.login()

        extra_data = {}
        if location:
            extra_data["location"] = location
        if disable_comments:
            extra_data["disable_comments"] = True

        try:
            self.client.photo_upload(
                media_path,
                caption=caption or "",
                extra_data=extra_data,
                usertags={},
            )

        except LoginRequired:
            self.login(force=True)

            self.client.photo_upload(
                media_path,
                caption=caption or "",
                extra_data=extra_data,
                usertags={},
            )

    # -------------------------
    # Reel post
    # -------------------------

    def post_reel(
        self,
        media_path: str,
        caption: str = "",
        share_to_feed: bool = True,
        location: str = None,
    ):
        self.login()

        extra_data = {"share_to_feed": bool(share_to_feed)}
        if location:
            extra_data["location"] = location

        try:
            self.client.clip_upload(
                media_path,
                caption=caption or "",
                extra_data=extra_data,
            )

        except LoginRequired:
            self.login(force=True)

            self.client.clip_upload(
                media_path,
                caption=caption or "",
                extra_data=extra_data,
            )

    # -------------------------
    # Story post (FIXED)
    # -------------------------

    def post_story(self, media_path: str):
        """
        Upload image or video as Instagram Story
        """
        self.login()

        ext = os.path.splitext(media_path.lower())[1]

        try:
            if ext in {".jpg", ".jpeg", ".png"}:
                self.client.photo_upload_to_story(media_path)

            elif ext in {".mp4", ".mov"}:
                self.client.video_upload_to_story(media_path)

            else:
                raise ValueError(f"Unsupported story media type: {media_path}")

        except LoginRequired:
            # SESSION EXPIRED → FORCE RELOGIN
            self.login(force=True)

            if ext in {".jpg", ".jpeg", ".png"}:
                self.client.photo_upload_to_story(media_path)

            elif ext in {".mp4", ".mov"}:
                self.client.video_upload_to_story(media_path)

    # -------------------------
    # Unified executor
    # -------------------------

    def execute_post(
        self,
        media_path: str,
        caption: str,
        post_type: str,
        share_to_feed: bool = True,
        **_,
    ):
        ext = os.path.splitext(media_path.lower())[1]
        is_video = ext in {".mp4", ".mov"}

        # SAFETY OVERRIDE
        if is_video and post_type == "feed":
            post_type = "reel"

        if post_type == "feed":
            self.post_feed(media_path, caption)

        elif post_type == "reel":
            self.post_reel(media_path, caption, share_to_feed)

        elif post_type == "story":
            self.post_story(media_path)

        else:
            raise ValueError(f"Unsupported post type: {post_type}")

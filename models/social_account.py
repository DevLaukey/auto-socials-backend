from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime
from app.models.base import Base


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id = Column(Integer, primary_key=True, index=True)

    platform = Column(String, nullable=False)  # instagram | youtube
    username = Column(String, nullable=False)

    # Encrypted at rest
    encrypted_password = Column(String, nullable=True)

    # Instagrapi / API session data
    session_blob = Column(JSON, nullable=True)

    status = Column(String, default="registered")
    last_login = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
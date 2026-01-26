from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.base import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)

    # Primary account (reference only – real mapping is posts_accounts)
    account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=False,
        index=True,
    )

    media_file = Column(String, nullable=False)

    title = Column(String)
    description = Column(String)
    hashtags = Column(String)

    tags = Column(String)
    privacy_status = Column(String)

    post_type = Column(String, default="feed")
    cover_image = Column(String)
    audio_name = Column(String)
    location = Column(String)

    disable_comments = Column(Integer, default=0)
    share_to_feed = Column(Integer, default=1)

    scheduled_time = Column(DateTime, nullable=True)
    status = Column(String, default="Pending", nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

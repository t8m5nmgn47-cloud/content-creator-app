from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    Float, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from app.database import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    url = Column(String(1000), unique=True, nullable=False)
    source = Column(String(200), default="")       # "newsapi", "rss", feed name
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    viral_score = Column(Float, default=0.0)        # 1–10, set by Claude
    processed = Column(Boolean, default=False)       # Has caption been generated

    posts = relationship("Post", back_populates="news_item")

    def __repr__(self):
        return f"<NewsItem id={self.id} title='{self.title[:50]}'>"


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    news_item_id = Column(Integer, ForeignKey("news_items.id"), nullable=True)
    platform = Column(String(50), default="twitter")  # twitter, linkedin, etc.
    caption = Column(Text, nullable=False)
    hashtags = Column(String(500), default="")
    hook = Column(String(300), default="")
    video_url = Column(String(1000), default="")
    status = Column(String(20), default="pending")    # pending/approved/posted/failed
    scheduled_for = Column(DateTime, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    platform_post_id = Column(String(200), default="")  # Tweet ID etc.
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    news_item = relationship("NewsItem", back_populates="posts")

    def __repr__(self):
        return f"<Post id={self.id} platform={self.platform} status={self.status}>"


class Niche(Base):
    __tablename__ = "niches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    keywords = Column(Text, default="")     # Comma-separated keywords
    enabled = Column(Boolean, default=True)
    posts_per_day = Column(Integer, default=2)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Niche id={self.id} name='{self.name}'>"


class AppLog(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), default="info")   # info / warning / error
    job = Column(String(100), default="")         # news_fetcher / claude_writer / etc.
    message = Column(Text, nullable=False)
    details = Column(Text, default="")            # JSON blob for extra data
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AppLog id={self.id} level={self.level} job={self.job}>"


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

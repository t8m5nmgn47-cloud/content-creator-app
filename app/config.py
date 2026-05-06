import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from dotenv import load_dotenv, find_dotenv

# Load .env from the project root regardless of working directory
_env_file = find_dotenv(usecwd=False) or ".env"
load_dotenv(_env_file, override=True)


class Settings(BaseSettings):
    # AI Services
    anthropic_api_key: str = ""
    runway_api_key: str = ""

    # News
    news_api_key: str = ""

    # Twitter / X
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    twitter_bearer_token: str = ""
    twitter_client_id: str = ""
    twitter_client_secret: str = ""

    # LinkedIn
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""

    # Meta
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_access_token: str = ""

    # TikTok
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""

    # YouTube
    youtube_client_id: str = ""
    youtube_client_secret: str = ""

    # Pinterest
    pinterest_access_token: str = ""

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "ContentCreatorApp/1.0"

    # App settings
    posts_per_day: int = 8
    timezone: str = "America/Chicago"
    auto_approve_posts: bool = True

    # Database — SQLite locally, PostgreSQL on Railway
    database_url: str = "sqlite:///./content_creator.db"

    class Config:
        env_file = ".env"
        extra = "ignore"

    def get_database_url(self) -> str:
        """Fix Railway's postgres:// prefix for SQLAlchemy."""
        url = os.getenv("DATABASE_URL", self.database_url)
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache()
def get_settings() -> Settings:
    return Settings()

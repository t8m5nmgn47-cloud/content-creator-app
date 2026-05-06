"""JSON API endpoints used by dashboard JavaScript."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppLog, NewsItem, Post
from app.scheduler import scheduler

router = APIRouter()


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    pending_count = db.query(Post).filter(Post.status == "pending").count()
    approved_count = db.query(Post).filter(Post.status == "approved").count()

    return {
        "scheduler_running": scheduler.running,
        "posts_today": db.query(Post).filter(
            Post.status == "posted", Post.posted_at >= today_start
        ).count(),
        "queue_size": pending_count + approved_count,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "news_items_total": db.query(NewsItem).count(),
        "last_fetch": db.query(AppLog)
            .filter(AppLog.job == "news_fetcher", AppLog.level == "info")
            .order_by(AppLog.created_at.desc())
            .first(),
    }


@router.get("/logs")
def get_logs(limit: int = 20, db: Session = Depends(get_db)):
    logs = (
        db.query(AppLog)
        .order_by(AppLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "level": log.level,
            "job": log.job,
            "message": log.message,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.post("/run/fetch-news")
def run_fetch_news():
    """Manually trigger news fetch."""
    from app.scheduler import _fetch_news_job
    scheduler.add_job(_fetch_news_job, id="manual_fetch_api", replace_existing=True)
    return {"status": "triggered"}


@router.post("/run/generate-posts")
def run_generate_posts():
    """Manually trigger post generation."""
    from app.scheduler import _generate_posts_job
    scheduler.add_job(_generate_posts_job, id="manual_generate_api", replace_existing=True)
    return {"status": "triggered"}

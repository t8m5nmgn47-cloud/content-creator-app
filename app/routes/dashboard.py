from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppLog, NewsItem, Post
from app.scheduler import scheduler

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Stats
    posts_today = db.query(Post).filter(
        Post.status == "posted",
        Post.posted_at >= today_start
    ).count()

    posts_week = db.query(Post).filter(
        Post.status == "posted",
        Post.posted_at >= now - timedelta(days=7)
    ).count()

    total_posted = db.query(Post).filter(Post.status == "posted").count()
    total_failed = db.query(Post).filter(Post.status == "failed").count()
    success_rate = round(total_posted / (total_posted + total_failed) * 100) if (total_posted + total_failed) > 0 else 100

    # Post queue (next 10 scheduled)
    queued_posts = (
        db.query(Post)
        .filter(Post.status.in_(["pending", "approved"]))
        .order_by(Post.scheduled_for.asc())
        .limit(10)
        .all()
    )

    # Recent posted
    recent_posts = (
        db.query(Post)
        .filter(Post.status == "posted")
        .order_by(Post.posted_at.desc())
        .limit(10)
        .all()
    )

    # Latest news
    latest_news = (
        db.query(NewsItem)
        .order_by(NewsItem.fetched_at.desc())
        .limit(6)
        .all()
    )

    # Recent logs
    recent_logs = (
        db.query(AppLog)
        .order_by(AppLog.created_at.desc())
        .limit(8)
        .all()
    )

    # Scheduler status
    scheduler_running = scheduler.running

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "posts_today": posts_today,
        "posts_week": posts_week,
        "success_rate": success_rate,
        "queued_posts": queued_posts,
        "recent_posts": recent_posts,
        "latest_news": latest_news,
        "recent_logs": recent_logs,
        "scheduler_running": scheduler_running,
        "now": now,
    })

"""
APScheduler setup — runs jobs inside the FastAPI process.
No Redis or separate worker needed.
"""
import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

tz = pytz.timezone(settings.timezone)
scheduler = BackgroundScheduler(timezone=tz)


def setup_jobs():
    """Register all scheduled jobs."""

    # ── Content Discovery ──────────────────────────────────────────
    # Fetch news every 3 hours
    scheduler.add_job(
        _fetch_news_job,
        CronTrigger(hour="*/3", minute=0, timezone=tz),
        id="fetch_news",
        replace_existing=True,
        name="Fetch News (NewsAPI + RSS)",
    )

    # Generate posts 30 min after each news fetch
    scheduler.add_job(
        _generate_posts_job,
        CronTrigger(hour="0,3,6,9,12,15,18,21", minute=30, timezone=tz),
        id="generate_posts",
        replace_existing=True,
        name="Generate Posts (Claude)",
    )

    # Generate videos 5 min after post generation (for viral_score >= 8 posts)
    scheduler.add_job(
        _generate_videos_job,
        CronTrigger(hour="0,3,6,9,12,15,18,21", minute=35, timezone=tz),
        id="generate_videos",
        replace_existing=True,
        name="Generate Videos (Runway)",
    )

    # ── Twitter Posting — 8x/day at peak hours (Central Time) ──────
    posting_times = [
        (7, 0),   # 7:00 AM — morning
        (9, 0),   # 9:00 AM — work start
        (11, 30), # 11:30 AM — pre-lunch
        (13, 0),  # 1:00 PM — lunch
        (15, 0),  # 3:00 PM — afternoon
        (17, 30), # 5:30 PM — commute home
        (19, 0),  # 7:00 PM — evening
        (21, 0),  # 9:00 PM — late night
    ]

    for i, (hour, minute) in enumerate(posting_times):
        scheduler.add_job(
            _post_twitter_job,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=f"twitter_post_{i}",
            replace_existing=True,
            name=f"Twitter Post {i+1}/8 ({hour:02d}:{minute:02d})",
        )

    # ── Maintenance ────────────────────────────────────────────────
    scheduler.add_job(
        _cleanup_logs_job,
        CronTrigger(hour=3, minute=0, timezone=tz),
        id="cleanup_logs",
        replace_existing=True,
        name="Cleanup Old Logs",
    )

    logger.info(f"Scheduler ready: {len(scheduler.get_jobs())} jobs registered")


# ── Job implementations ────────────────────────────────────────────

def _fetch_news_job():
    try:
        from app.services.news_fetcher import fetch_news
        fetch_news()
    except Exception as e:
        logger.error(f"fetch_news_job error: {e}")


def _generate_posts_job():
    try:
        from app.services.claude_writer import generate_posts_for_queue
        generate_posts_for_queue()
    except Exception as e:
        logger.error(f"generate_posts_job error: {e}")


def _post_twitter_job():
    try:
        from app.services.twitter_poster import post_next_in_queue
        post_next_in_queue()
    except Exception as e:
        logger.error(f"post_twitter_job error: {e}")


def _generate_videos_job():
    try:
        from app.services.claude_writer import generate_videos_for_queue
        generate_videos_for_queue()
    except Exception as e:
        logger.error(f"generate_videos_job error: {e}")


def _cleanup_logs_job():
    try:
        from datetime import datetime, timedelta
        from app.database import SessionLocal
        from app.models import AppLog
        db = SessionLocal()
        cutoff = datetime.utcnow() - timedelta(days=30)
        deleted = db.query(AppLog).filter(AppLog.created_at < cutoff).delete()
        db.commit()
        db.close()
        logger.info(f"Cleaned up {deleted} log entries older than 30 days")
    except Exception as e:
        logger.error(f"cleanup_logs_job error: {e}")

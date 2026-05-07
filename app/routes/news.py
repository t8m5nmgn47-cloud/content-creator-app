"""
News page — browse all fetched articles, generate posts or videos from any one.
"""
import json
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppLog, NewsItem, Post

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/news", response_class=HTMLResponse)
def news_page(
    request: Request,
    search: str = "",
    source: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    per_page = 30
    query = db.query(NewsItem).order_by(NewsItem.fetched_at.desc())

    if search:
        query = query.filter(NewsItem.title.ilike(f"%{search}%"))
    if source:
        query = query.filter(NewsItem.source.ilike(f"%{source}%"))

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    # Get unique sources for the filter dropdown
    sources = [
        row[0] for row in db.query(NewsItem.source).distinct().order_by(NewsItem.source).all()
    ]

    return templates.TemplateResponse("news.html", {
        "request": request,
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "search": search,
        "source": source,
        "sources": sources,
    })


@router.post("/news/{item_id}/generate-post")
async def generate_post_from_article(
    item_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Generate a Twitter post from a specific news item immediately."""
    item = db.query(NewsItem).filter(NewsItem.id == item_id).first()
    if not item:
        return JSONResponse({"error": "Article not found"}, status_code=404)

    # Reset processed flag so the writer picks it up
    item.processed = False
    db.commit()

    # Run in background so the response returns immediately
    background_tasks.add_task(_generate_post_task, item_id)

    return JSONResponse({"status": "generating", "item_id": item_id})


@router.post("/news/{item_id}/generate-video")
async def generate_video_from_article(
    item_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Generate a Runway video for a specific news item."""
    item = db.query(NewsItem).filter(NewsItem.id == item_id).first()
    if not item:
        return JSONResponse({"error": "Article not found"}, status_code=404)

    background_tasks.add_task(_generate_video_task, item_id)

    return JSONResponse({"status": "generating_video", "item_id": item_id,
                         "message": "Video generation started — takes 1-2 minutes"})


@router.get("/news/{item_id}/status")
def get_item_status(item_id: int, db: Session = Depends(get_db)):
    """Check if a post or video has been generated for this item."""
    item = db.query(NewsItem).filter(NewsItem.id == item_id).first()
    if not item:
        return JSONResponse({"error": "Not found"}, status_code=404)

    posts = db.query(Post).filter(Post.news_item_id == item_id).all()

    return {
        "item_id": item_id,
        "processed": item.processed,
        "posts": [
            {
                "id": p.id,
                "platform": p.platform,
                "status": p.status,
                "caption": p.caption[:100],
                "video_url": p.video_url,
            }
            for p in posts
        ],
    }


# ── Background tasks ───────────────────────────────────────────────

def _generate_post_task(item_id: int):
    from app.database import SessionLocal
    from app.services.claude_writer import generate_twitter_post, _next_schedule_slot
    from app.config import get_settings

    settings = get_settings()
    db = SessionLocal()
    try:
        item = db.query(NewsItem).filter(NewsItem.id == item_id).first()
        if not item:
            return

        result = generate_twitter_post(item.title, item.description)
        viral_score = float(result.get("viral_score", 5))

        item.viral_score = viral_score
        item.processed = True

        status = "approved" if settings.auto_approve_posts else "pending"
        scheduled = _next_schedule_slot(db)

        post = Post(
            news_item_id=item.id,
            platform="twitter",
            caption=result.get("caption", ""),
            hashtags=", ".join(result.get("hashtags", [])),
            hook=result.get("hook", ""),
            status=status,
            scheduled_for=scheduled,
        )
        db.add(post)

        db.add(AppLog(
            level="info",
            job="news_page",
            message=f"Generated post for article: {item.title[:60]}",
        ))
        db.commit()
        logger.info(f"Generated post for item {item_id}")

    except Exception as e:
        logger.error(f"_generate_post_task failed for item {item_id}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _generate_video_task(item_id: int):
    from app.database import SessionLocal
    from app.services.runway_client import generate_video, build_video_prompt
    from app.services.claude_writer import generate_twitter_post, _next_schedule_slot
    from app.config import get_settings

    settings = get_settings()
    db = SessionLocal()
    post = None
    try:
        item = db.query(NewsItem).filter(NewsItem.id == item_id).first()
        if not item:
            return

        # ── Create a "processing" post immediately so it's visible in the UI ──
        post = Post(
            news_item_id=item.id,
            platform="twitter",
            caption=f"🎬 Generating video for: {item.title[:80]}...",
            status="processing",
        )
        db.add(post)
        db.add(AppLog(
            level="info",
            job="runway",
            message=f"Video generation started: {item.title[:60]}",
        ))
        db.commit()

        # ── Generate the video ─────────────────────────────────────────────
        prompt = build_video_prompt(item.title, item.description)
        logger.info(f"Generating video for item {item_id}: {prompt[:80]}")
        video_url = generate_video(prompt)

        if not video_url:
            if not settings.runway_api_key:
                logger.info(f"No Runway key — generating text-only post for item {item_id}")
            else:
                db.add(AppLog(level="error", job="runway", message=f"Video generation failed for item {item_id}"))

        # ── Generate caption (with or without video) ───────────────────────

        # ── Generate caption and finalize the post (video optional) ───────
        caption_result = generate_twitter_post(item.title, item.description)
        final_status = "approved" if settings.auto_approve_posts else "pending"
        scheduled = _next_schedule_slot(db)

        post.caption = caption_result.get("caption", "")
        post.hashtags = ", ".join(caption_result.get("hashtags", []))
        post.hook = caption_result.get("hook", "")
        post.video_url = video_url
        post.status = final_status
        post.scheduled_for = scheduled

        item.processed = True
        item.viral_score = float(caption_result.get("viral_score", 5))

        db.add(AppLog(
            level="info",
            job="runway",
            message=f"Video ready: {item.title[:60]}",
            details=json.dumps({"video_url": video_url}),
        ))
        db.commit()
        logger.info(f"Video generated for item {item_id}: {video_url}")

    except Exception as e:
        logger.error(f"_generate_video_task failed for item {item_id}: {e}")
        try:
            db.rollback()
            if post and post.id:
                post.status = "failed"
                post.error_message = str(e)[:500]
            db.add(AppLog(level="error", job="runway", message=str(e)))
            db.commit()
        except Exception:
            pass
    finally:
        db.close()

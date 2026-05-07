import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Post, AppLog

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/trending", response_class=HTMLResponse)
def trending_page(request: Request):
    from app.services.trend_analyzer import get_trending_snapshot
    snapshot = get_trending_snapshot()

    updated_at = None
    if snapshot.get("updated_at"):
        try:
            updated_at = datetime.fromisoformat(snapshot["updated_at"])
        except Exception:
            pass

    return templates.TemplateResponse("trending.html", {
        "request": request,
        "clusters": snapshot.get("clusters", []),
        "updated_at": updated_at,
        "reddit_posts_count": snapshot.get("reddit_posts_count", 0),
        "headlines_count": snapshot.get("headlines_count", 0),
        "has_data": bool(snapshot.get("clusters")),
    })


@router.post("/trending/refresh")
def trending_refresh(request: Request):
    """Manually trigger a trend analysis refresh."""
    from app.services.trend_analyzer import refresh_trending_snapshot
    try:
        refresh_trending_snapshot()
    except Exception:
        pass
    return RedirectResponse(url="/trending", status_code=303)


@router.post("/trending/create-post")
async def create_post_from_trend(request: Request):
    """Generate a tweet for a trend cluster. Returns JSON for the review modal."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    topic = body.get("topic", "")
    summary = body.get("summary", "")
    hook = body.get("hook", "")
    best_angle = body.get("best_angle", "")

    if not topic:
        return JSONResponse({"error": "Missing topic"}, status_code=400)

    from app.services.claude_writer import generate_post_from_trend
    try:
        result = generate_post_from_trend(topic, summary, hook, best_angle)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/trending/save-post")
async def save_post_from_trend(request: Request, db: Session = Depends(get_db)):
    """Save a reviewed trend post to the queue (and optionally post immediately)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    caption = (body.get("caption") or "").strip()
    hashtags = (body.get("hashtags") or "").strip()
    post_now = body.get("post_now", False)

    if not caption:
        return JSONResponse({"error": "Caption is required"}, status_code=400)

    from datetime import timedelta
    from app.services.claude_writer import _next_schedule_slot

    scheduled = datetime.utcnow() + timedelta(minutes=5) if post_now else _next_schedule_slot(db)

    post = Post(
        news_item_id=None,
        platform="twitter",
        caption=caption,
        hashtags=hashtags,
        hook="",
        status="approved",
        scheduled_for=scheduled,
    )
    db.add(post)
    db.add(AppLog(
        level="info",
        job="trending",
        message=f"Post created from trending topic",
    ))
    db.commit()
    db.refresh(post)

    if post_now:
        from app.services.twitter_poster import post_tweet
        success = post_tweet(post.id)
        return JSONResponse({"post_id": post.id, "posted": success})

    return JSONResponse({"post_id": post.id, "posted": False})

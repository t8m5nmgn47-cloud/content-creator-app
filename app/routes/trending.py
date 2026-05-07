import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSetting, Post, AppLog

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

DISMISSED_KEY = "dismissed_trend_topics"


def _get_dismissed(db: Session) -> set:
    row = db.query(AppSetting).filter(AppSetting.key == DISMISSED_KEY).first()
    if not row or not row.value:
        return set()
    try:
        return set(json.loads(row.value))
    except Exception:
        return set()


def _save_dismissed(db: Session, dismissed: set):
    row = db.query(AppSetting).filter(AppSetting.key == DISMISSED_KEY).first()
    value = json.dumps(sorted(dismissed))
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=DISMISSED_KEY, value=value))
    db.commit()


@router.get("/trending", response_class=HTMLResponse)
def trending_page(request: Request, db: Session = Depends(get_db)):
    from app.services.trend_analyzer import get_trending_snapshot
    snapshot = get_trending_snapshot()

    updated_at = None
    if snapshot.get("updated_at"):
        try:
            updated_at = datetime.fromisoformat(snapshot["updated_at"])
        except Exception:
            pass

    dismissed = _get_dismissed(db)
    all_clusters = snapshot.get("clusters", [])
    clusters = [c for c in all_clusters if c.get("topic", "").lower() not in dismissed]

    # Load all posts created from the trending board, newest first
    trend_posts = (
        db.query(Post)
        .filter(Post.hook.like("trend:%"))
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )

    posted_topics = set()
    for p in trend_posts:
        if p.hook and p.hook.startswith("trend:"):
            posted_topics.add(p.hook[len("trend:"):].lower())

    return templates.TemplateResponse("trending.html", {
        "request": request,
        "clusters": clusters,
        "dismissed_count": len(dismissed),
        "updated_at": updated_at,
        "reddit_posts_count": snapshot.get("reddit_posts_count", 0),
        "headlines_count": snapshot.get("headlines_count", 0),
        "has_data": bool(all_clusters),
        "trend_posts": trend_posts,
        "posted_topics": posted_topics,
    })


@router.post("/trending/dismiss")
async def dismiss_topic(request: Request, db: Session = Depends(get_db)):
    """Add a topic to the dismissed list. Called via fetch — returns JSON."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)
    topic = (body.get("topic") or "").strip().lower()
    if not topic:
        return JSONResponse({"error": "Missing topic"}, status_code=400)
    dismissed = _get_dismissed(db)
    dismissed.add(topic)
    _save_dismissed(db, dismissed)
    return JSONResponse({"ok": True, "dismissed_count": len(dismissed)})


@router.post("/trending/restore-dismissed")
def restore_dismissed(db: Session = Depends(get_db)):
    """Clear the entire dismissed list."""
    _save_dismissed(db, set())
    return RedirectResponse(url="/trending", status_code=303)



@router.get("/trending", response_class=HTMLResponse)
def trending_page(request: Request, db: Session = Depends(get_db)):
    from app.services.trend_analyzer import get_trending_snapshot
    snapshot = get_trending_snapshot()

    updated_at = None
    if snapshot.get("updated_at"):
        try:
            updated_at = datetime.fromisoformat(snapshot["updated_at"])
        except Exception:
            pass

    # Load all posts created from the trending board, newest first
    trend_posts = (
        db.query(Post)
        .filter(Post.hook.like("trend:%"))
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )

    # Build a set of topic slugs that have been posted about
    posted_topics = set()
    for p in trend_posts:
        if p.hook and p.hook.startswith("trend:"):
            posted_topics.add(p.hook[len("trend:"):].lower())

    return templates.TemplateResponse("trending.html", {
        "request": request,
        "clusters": snapshot.get("clusters", []),
        "updated_at": updated_at,
        "reddit_posts_count": snapshot.get("reddit_posts_count", 0),
        "headlines_count": snapshot.get("headlines_count", 0),
        "has_data": bool(snapshot.get("clusters")),
        "trend_posts": trend_posts,
        "posted_topics": posted_topics,
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

    topic = (body.get("topic") or "").strip()

    post = Post(
        news_item_id=None,
        platform="twitter",
        caption=caption,
        hashtags=hashtags,
        hook=f"trend:{topic}" if topic else "trend",
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

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Post, AppLog
from app.scheduler import scheduler

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/posts", response_class=HTMLResponse)
def posts_page(
    request: Request,
    filter: str = "all",
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    per_page = 25
    query = db.query(Post)

    if filter == "processing":
        query = query.filter(Post.status == "processing")
    elif filter == "pending":
        query = query.filter(Post.status == "pending")
    elif filter == "approved":
        query = query.filter(Post.status == "approved")
    elif filter == "posted":
        query = query.filter(Post.status == "posted")
    elif filter == "failed":
        query = query.filter(Post.status == "failed")
    elif filter == "skipped":
        query = query.filter(Post.status == "skipped")

    if search:
        query = query.filter(Post.caption.ilike(f"%{search}%"))

    total = query.count()
    posts = query.order_by(Post.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("posts.html", {
        "request": request,
        "posts": posts,
        "filter": filter,
        "search": search,
        "page": page,
        "pages": pages,
        "total": total,
    })


@router.post("/posts/{post_id}/approve")
def approve_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        post.status = "approved"
        db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@router.post("/posts/{post_id}/skip")
def skip_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        post.status = "skipped"
        post.error_message = ""
        db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@router.post("/posts/{post_id}/retry")
def retry_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        post.status = "approved"
        post.error_message = ""
        db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@router.get("/posts/{post_id}/edit")
def get_post_for_edit(post_id: int, db: Session = Depends(get_db)):
    """Return post data as JSON for the edit modal."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        return JSONResponse({"error": "Post not found"}, status_code=404)
    return {
        "id": post.id,
        "caption": post.caption,
        "hashtags": post.hashtags,
        "scheduled_for": post.scheduled_for.strftime("%Y-%m-%dT%H:%M") if post.scheduled_for else "",
    }


@router.post("/posts/{post_id}/edit")
def save_post_edit(
    post_id: int,
    caption: str = Form(...),
    hashtags: str = Form(""),
    scheduled_for: str = Form(""),
    db: Session = Depends(get_db),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        return RedirectResponse(url="/posts", status_code=303)

    post.caption = caption.strip()
    post.hashtags = hashtags.strip()

    if scheduled_for:
        from datetime import datetime
        try:
            post.scheduled_for = datetime.fromisoformat(scheduled_for)
        except ValueError:
            pass

    db.add(AppLog(
        level="info",
        job="posts",
        message=f"Post {post_id} manually edited",
    ))
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@router.post("/posts/{post_id}/mark-posted")
def mark_posted(post_id: int, db: Session = Depends(get_db)):
    """Manually mark a post as already sent (e.g. posted directly on Twitter)."""
    from datetime import datetime
    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        post.status = "posted"
        post.posted_at = datetime.utcnow()
        post.error_message = ""
        db.add(AppLog(
            level="info",
            job="posts",
            message=f"Post {post_id} manually marked as posted",
        ))
        db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/posts/{post_id}/post-now")
def post_now(post_id: int, db: Session = Depends(get_db)):
    """Send a specific post immediately, bypassing the schedule."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        post.status = "approved"
        db.commit()
        from app.services.twitter_poster import post_tweet
        post_tweet(post_id)
    return RedirectResponse(url="/posts", status_code=303)


@router.post("/posts/compose")
async def compose_post(request: Request, db: Session = Depends(get_db)):
    """Take a user draft and return 4 Claude-polished variations."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    draft = (body.get("draft") or "").strip()
    if not draft:
        return JSONResponse({"error": "Draft cannot be empty"}, status_code=400)

    from app.services.claude_writer import improve_post_draft
    try:
        result = improve_post_draft(draft)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/posts/compose/save")
async def save_composed_post(request: Request, db: Session = Depends(get_db)):
    """Save a composed post to the queue."""
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
        hook="composed",
        status="approved",
        scheduled_for=scheduled,
    )
    db.add(post)
    db.add(AppLog(level="info", job="posts", message="Post created via compose"))
    db.commit()
    db.refresh(post)

    if post_now:
        from app.services.twitter_poster import post_tweet
        success = post_tweet(post.id)
        return JSONResponse({"post_id": post.id, "posted": success})

    return JSONResponse({"post_id": post.id, "posted": False})


@router.post("/posts/generate-now")
def generate_now():
    """Manually trigger one content generation cycle."""
    from app.scheduler import _fetch_news_job, _generate_posts_job
    scheduler.add_job(_fetch_news_job, id="manual_fetch", replace_existing=True)
    scheduler.add_job(_generate_posts_job, id="manual_generate", replace_existing=True)
    return RedirectResponse(url="/posts", status_code=303)

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
        post.status = "failed"
        post.error_message = "Manually skipped"
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


@router.post("/posts/generate-now")
def generate_now():
    """Manually trigger one content generation cycle."""
    from app.scheduler import _fetch_news_job, _generate_posts_job
    scheduler.add_job(_fetch_news_job, id="manual_fetch", replace_existing=True)
    scheduler.add_job(_generate_posts_job, id="manual_generate", replace_existing=True)
    return RedirectResponse(url="/posts", status_code=303)

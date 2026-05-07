from typing import List
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AppSetting
from app.services.content_filter import (
    TOPIC_CATEGORIES,
    get_blocked_categories,
    save_blocked_categories,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    auto_approve = _get_setting(db, "auto_approve", "true") == "true"
    posts_per_day = int(_get_setting(db, "posts_per_day", str(settings.posts_per_day)))

    # API key status — just check if they're set
    api_status = {
        "anthropic": bool(settings.anthropic_api_key),
        "runway": bool(settings.runway_api_key),
        "newsapi": bool(settings.news_api_key),
        "twitter": bool(settings.twitter_api_key),
        "linkedin": bool(settings.linkedin_client_id),
        "meta": bool(settings.meta_app_id),
        "tiktok": bool(settings.tiktok_client_key),
        "youtube": bool(settings.youtube_client_id),
        "pinterest": bool(settings.pinterest_access_token),
    }

    blocked_categories = get_blocked_categories(db)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "auto_approve": auto_approve,
        "posts_per_day": posts_per_day,
        "api_status": api_status,
        "topic_categories": TOPIC_CATEGORIES,
        "blocked_categories": blocked_categories,
    })


@router.post("/settings/save")
def save_settings(
    request: Request,
    auto_approve: str = Form("false"),
    posts_per_day: int = Form(8),
    db: Session = Depends(get_db),
):
    _set_setting(db, "auto_approve", auto_approve)
    _set_setting(db, "posts_per_day", str(posts_per_day))

    # Content filters — collect checked category checkboxes from form
    form_data = request.headers  # we'll read via POST body below
    return RedirectResponse(url="/settings?saved=1", status_code=303)


@router.post("/settings/filters")
async def save_filters(
    request: Request,
    db: Session = Depends(get_db),
):
    """Save the content topic blocklist. Checkboxes send their values only when checked."""
    form = await request.form()
    checked = form.getlist("blocked_categories")
    save_blocked_categories(db, checked)
    return RedirectResponse(url="/settings?saved=1", status_code=303)

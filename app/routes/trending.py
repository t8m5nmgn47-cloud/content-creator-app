from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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

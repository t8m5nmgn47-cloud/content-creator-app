from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Niche

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/niches", response_class=HTMLResponse)
def niches_page(request: Request, db: Session = Depends(get_db)):
    niches = db.query(Niche).order_by(Niche.created_at.desc()).all()
    return templates.TemplateResponse("niches.html", {
        "request": request,
        "niches": niches,
    })


@router.post("/niches/add")
def add_niche(
    name: str = Form(...),
    description: str = Form(""),
    keywords: str = Form(""),
    db: Session = Depends(get_db),
):
    niche = Niche(name=name, description=description, keywords=keywords)
    db.add(niche)
    db.commit()
    return RedirectResponse(url="/niches", status_code=303)


@router.post("/niches/{niche_id}/toggle")
def toggle_niche(niche_id: int, db: Session = Depends(get_db)):
    niche = db.query(Niche).filter(Niche.id == niche_id).first()
    if niche:
        niche.enabled = not niche.enabled
        db.commit()
    return RedirectResponse(url="/niches", status_code=303)


@router.post("/niches/{niche_id}/delete")
def delete_niche(niche_id: int, db: Session = Depends(get_db)):
    niche = db.query(Niche).filter(Niche.id == niche_id).first()
    if niche:
        db.delete(niche)
        db.commit()
    return RedirectResponse(url="/niches", status_code=303)


@router.get("/niches/suggest")
def suggest_niches_api():
    """Ask Claude to suggest trending niches — returns JSON."""
    from app.services.claude_writer import suggest_niches
    try:
        suggestions = suggest_niches()
        return {"suggestions": suggestions}
    except Exception as e:
        return {"error": str(e)}

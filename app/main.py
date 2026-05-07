"""
Content Creator App — Main FastAPI entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app import models  # noqa: F401 — ensures models are registered
from app.scheduler import scheduler, setup_jobs
from app.routes import dashboard, posts, niches, news, settings, api, trending

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────
    logger.info("🚀 Content Creator starting up...")

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables ready")

    # Seed default niches if none exist
    _seed_default_niches()

    # Start the scheduler
    setup_jobs()
    scheduler.start()
    logger.info(f"✅ Scheduler started with {len(scheduler.get_jobs())} jobs")

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    logger.info("🛑 Shutting down scheduler...")
    scheduler.shutdown(wait=False)
    logger.info("👋 Content Creator shut down cleanly")


app = FastAPI(
    title="Content Creator",
    description="Automated content creation and social media posting",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routes
app.include_router(dashboard.router)
app.include_router(posts.router)
app.include_router(niches.router)
app.include_router(news.router)
app.include_router(settings.router)
app.include_router(trending.router)
app.include_router(api.router, prefix="/api")


@app.get("/health")
def health():
    """Railway health check endpoint."""
    return {"status": "ok"}


def _seed_default_niches():
    """Add starter niches if the table is empty."""
    from app.database import SessionLocal
    from app.models import Niche

    db = SessionLocal()
    try:
        if db.query(Niche).count() == 0:
            defaults = [
                Niche(
                    name="Technology & AI",
                    description="Artificial intelligence, software, gadgets, and tech news",
                    keywords="AI, artificial intelligence, tech, software, robots, ChatGPT, automation",
                    enabled=True,
                    posts_per_day=3,
                ),
                Niche(
                    name="Business & Finance",
                    description="Markets, startups, economy, and business news",
                    keywords="stocks, economy, startup, business, markets, investment, finance",
                    enabled=True,
                    posts_per_day=2,
                ),
                Niche(
                    name="Health & Wellness",
                    description="Medical breakthroughs, fitness, and wellness trends",
                    keywords="health, medicine, fitness, wellness, study, research, diet",
                    enabled=True,
                    posts_per_day=2,
                ),
                Niche(
                    name="Entertainment",
                    description="Movies, music, celebrities, and pop culture",
                    keywords="movie, music, celebrity, entertainment, viral, trending",
                    enabled=False,
                    posts_per_day=1,
                ),
            ]
            for niche in defaults:
                db.add(niche)
            db.commit()
            logger.info("✅ Seeded 4 default niches")
    finally:
        db.close()

"""
News Fetcher — pulls headlines from NewsAPI and RSS feeds.
Deduplicates by URL and stores new items in the database.
"""
import html as html_lib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx
from newsapi import NewsApiClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppLog, NewsItem

logger = logging.getLogger(__name__)
settings = get_settings()

_HTML_TAG_RE = re.compile(r'<[^>]+>')

def _clean_description(text: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(' ', text)
    text = html_lib.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# RSS User-Agent (some feeds block the default feedparser UA)
RSS_UA = "Mozilla/5.0 (compatible; ContentBot/1.0)"

# Hard news sources only — no gadget blogs or deal sites
RSS_FEEDS = [
    # Wire services & broadcast
    ("Reuters World",       "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Business",    "https://feeds.reuters.com/reuters/businessNews"),
    ("AP Top News",         "https://rsshub.app/apnews/topics/apf-topnews"),
    ("NPR Top Stories",     "https://feeds.npr.org/1001/rss.xml"),
    ("BBC World",           "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Technology",      "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    # Newspapers
    ("NY Times World",      "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("NY Times Business",   "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("NY Times Tech",       "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
    ("The Guardian World",  "https://www.theguardian.com/world/rss"),
    ("The Guardian Tech",   "https://www.theguardian.com/technology/rss"),
    # Tech — analysis, not deals
    ("Ars Technica",        "http://feeds.arstechnica.com/arstechnica/index"),
    ("MIT Tech Review",     "https://www.technologyreview.com/feed/"),
    ("Hacker News",         "https://hnrss.org/frontpage"),
    # Finance
    ("CNBC Top News",       "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
]

# Keywords that indicate ad/deal/product content — skip these stories
AD_KEYWORDS = [
    "deal", "deals", "sale", "discount", "off", "price drop", "lowest price",
    "best buy", "amazon", "coupon", "promo", "offer", "limited time",
    "buy now", "in stock", "out of stock", "restock", "charger", "accessory",
    "accessories", "review:", "hands-on", "unboxing", "vs.", " vs ",
    "best ", "top 10", "top 5", "ranked", "buying guide",
]

# NewsAPI categories to pull from
NEWS_CATEGORIES = ["technology", "business", "entertainment", "health", "science"]


def _log(db: Session, level: str, message: str, details: dict = None):
    """Write a log entry to the database."""
    entry = AppLog(
        level=level,
        job="news_fetcher",
        message=message,
        details=json.dumps(details or {}),
    )
    db.add(entry)
    db.commit()


def _save_item(db: Session, title: str, description: str, url: str,
               source: str, published_at: Optional[datetime]) -> bool:
    """Save a news item if not already in the DB. Returns True if new."""
    if not title or not url:
        return False
    title_lower = title.lower()
    if any(kw in title_lower for kw in AD_KEYWORDS):
        return False
    # Topic blocklist — user-configurable via Settings
    from app.services.content_filter import get_blocked_categories, is_blocked
    blocked = get_blocked_categories(db)
    if blocked and is_blocked(title, blocked):
        return False
    existing = db.query(NewsItem).filter(NewsItem.url == url).first()
    if existing:
        return False
    item = NewsItem(
        title=title[:500],
        description=_clean_description(description)[:2000],
        url=url[:1000],
        source=source,
        published_at=published_at,
        fetched_at=datetime.utcnow(),
    )
    db.add(item)
    try:
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def fetch_from_newsapi(db: Session) -> int:
    """Fetch top headlines from NewsAPI across all categories."""
    if not settings.news_api_key:
        logger.warning("NEWS_API_KEY not set — skipping NewsAPI fetch")
        return 0

    client = NewsApiClient(api_key=settings.news_api_key)
    new_count = 0

    for category in NEWS_CATEGORIES:
        try:
            response = client.get_top_headlines(
                category=category,
                language="en",
                country="us",
                page_size=10,
            )
            articles = response.get("articles", [])
            for article in articles:
                published = None
                if article.get("publishedAt"):
                    try:
                        published = datetime.fromisoformat(
                            article["publishedAt"].replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        pass

                saved = _save_item(
                    db=db,
                    title=article.get("title", ""),
                    description=article.get("description", "") or article.get("content", ""),
                    url=article.get("url", ""),
                    source=f"newsapi:{category}",
                    published_at=published,
                )
                if saved:
                    new_count += 1
        except Exception as e:
            logger.error(f"NewsAPI error for category {category}: {e}")
            _log(db, "error", f"NewsAPI fetch failed for {category}: {str(e)}")

    logger.info(f"NewsAPI: fetched {new_count} new articles")
    return new_count


def fetch_from_rss(db: Session) -> int:
    """Fetch articles from all configured RSS feeds.
    Uses httpx with a browser-like User-Agent so feeds don't block us.
    """
    new_count = 0

    for feed_name, feed_url in RSS_FEEDS:
        try:
            # Fetch with httpx first (many feeds block feedparser's default UA)
            r = httpx.get(
                feed_url,
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": RSS_UA},
            )
            if r.status_code != 200:
                logger.warning(f"RSS {feed_name}: HTTP {r.status_code}")
                continue

            feed = feedparser.parse(r.content)
            entries = feed.entries[:15]  # max 15 per feed

            for entry in entries:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass

                title = getattr(entry, "title", "")
                description = getattr(entry, "summary", "") or getattr(entry, "description", "")
                url = getattr(entry, "link", "")

                saved = _save_item(
                    db=db,
                    title=title,
                    description=description,
                    url=url,
                    source=f"rss:{feed_name}",
                    published_at=published,
                )
                if saved:
                    new_count += 1

            if entries:
                logger.info(f"RSS {feed_name}: {len(entries)} checked, {new_count} new so far")

        except Exception as e:
            logger.error(f"RSS error for {feed_name}: {e}")

    logger.info(f"RSS: fetched {new_count} new articles total")
    return new_count


def fetch_news():
    """
    Main entry point — called by the scheduler every 3 hours.
    Fetches from all sources and logs the result.
    """
    db = SessionLocal()
    try:
        logger.info("Starting news fetch...")
        newsapi_count = fetch_from_newsapi(db)
        rss_count = fetch_from_rss(db)
        total = newsapi_count + rss_count
        _log(db, "info", f"News fetch complete: {total} new articles ({newsapi_count} from NewsAPI, {rss_count} from RSS)")
        logger.info(f"News fetch complete: {total} total new articles")
        return total
    except Exception as e:
        logger.error(f"fetch_news failed: {e}")
        try:
            _log(db, "error", f"News fetch failed: {str(e)}")
        except Exception:
            pass
        return 0
    finally:
        db.close()

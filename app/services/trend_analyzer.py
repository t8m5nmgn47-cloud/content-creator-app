"""
Trend Analyzer — finds trending story patterns from Reddit + DB news items.
Asks Claude Sonnet to identify clusters, angles, and hooks.
Stores the result as a JSON snapshot in AppSetting so the page loads fast.
"""
import json
import logging
from datetime import datetime, timedelta

import httpx
import anthropic

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting, NewsItem

logger = logging.getLogger(__name__)
settings = get_settings()

REDDIT_UA = "ContentCreatorApp/1.0 (trend analysis bot)"

REDDIT_SUBS = [
    "worldnews",
    "technology",
    "business",
    "science",
    "politics",
    "Futurology",
]

SNAPSHOT_KEY = "trending_snapshot"


def _fetch_reddit_hot(subreddit: str, limit: int = 15) -> list[dict]:
    """Pull hot posts from a subreddit via the public JSON API. No auth needed."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        r = httpx.get(url, timeout=10, headers={"User-Agent": REDDIT_UA},
                      follow_redirects=True)
        if r.status_code != 200:
            logger.warning(f"Reddit r/{subreddit}: HTTP {r.status_code}")
            return []
        data = r.json()
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            if p.get("stickied") or p.get("is_self") is False and not p.get("url"):
                continue
            posts.append({
                "title": p.get("title", ""),
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "subreddit": p.get("subreddit", subreddit),
            })
        return posts
    except Exception as e:
        logger.warning(f"Reddit fetch failed for r/{subreddit}: {e}")
        return []


def _get_recent_headlines(db) -> list[str]:
    """Pull headlines stored in the DB from the last 6 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=6)
    items = (
        db.query(NewsItem)
        .filter(NewsItem.fetched_at >= cutoff)
        .order_by(NewsItem.fetched_at.desc())
        .limit(60)
        .all()
    )
    return [item.title for item in items]


def _ask_claude_for_trends(reddit_posts: list[dict], headlines: list[str]) -> list[dict]:
    """Send aggregated data to Claude Sonnet and get back trend clusters."""
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key — skipping trend analysis")
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Format Reddit posts
    reddit_section = ""
    if reddit_posts:
        lines = []
        for p in reddit_posts[:40]:
            lines.append(
                f"[r/{p['subreddit']}] {p['title']} "
                f"(score: {p['score']}, comments: {p['num_comments']})"
            )
        reddit_section = "\n".join(lines)
    else:
        reddit_section = "(Reddit unavailable)"

    # Format DB headlines
    headlines_section = "\n".join(headlines[:50]) if headlines else "(No recent news in DB)"

    prompt = f"""You are a social media trend analyst. I'll give you two real-time data sources:

## Reddit Hot Posts (right now)
{reddit_section}

## News Headlines (last 6 hours from wire services)
{headlines_section}

Identify 5–8 distinct trending story CLUSTERS. A cluster is a group of related posts/headlines about the same underlying story or topic.

For each cluster, respond with JSON:
{{
  "topic": "Short topic label (max 6 words)",
  "summary": "One sentence explaining what's happening and why it matters",
  "why_trending": "Why this is gaining traction on social media right now",
  "momentum": 8,
  "best_angle": "The angle most likely to drive retweets — what unique spin to take",
  "hook": "A punchy opening tweet hook (max 120 chars, no hashtags)",
  "sources": ["source1", "source2"]
}}

Rules:
- momentum is 1–10 based on Reddit scores + headline volume
- best_angle should be counterintuitive or emotionally engaging
- hook should feel like something a smart person would say, not a headline recap
- sources lists where you saw it (subreddit names or news outlet names)
- Skip pure celebrity gossip; focus on news that has real-world implications

Respond with ONLY a valid JSON array of these objects. No markdown, no extra text."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    clusters = json.loads(raw)
    # Sort by momentum descending
    clusters.sort(key=lambda c: c.get("momentum", 0), reverse=True)
    return clusters


def refresh_trending_snapshot() -> dict:
    """
    Main entry point — called by scheduler every 30 min.
    Fetches Reddit + DB headlines, runs Claude analysis, saves snapshot.
    Returns the snapshot dict.
    """
    db = SessionLocal()
    try:
        # Gather data
        reddit_posts = []
        for sub in REDDIT_SUBS:
            reddit_posts.extend(_fetch_reddit_hot(sub, limit=15))

        headlines = _get_recent_headlines(db)

        logger.info(
            f"Trend analysis: {len(reddit_posts)} Reddit posts, "
            f"{len(headlines)} headlines"
        )

        clusters = _ask_claude_for_trends(reddit_posts, headlines)

        # Strip out clusters that match the user's topic blocklist
        from app.services.content_filter import get_blocked_categories, is_blocked
        blocked = get_blocked_categories(db)
        if blocked:
            clusters = [
                c for c in clusters
                if not is_blocked(c.get("topic", "") + " " + c.get("summary", ""), blocked)
            ]

        snapshot = {
            "updated_at": datetime.utcnow().isoformat(),
            "reddit_posts_count": len(reddit_posts),
            "headlines_count": len(headlines),
            "clusters": clusters,
        }

        # Persist to AppSetting
        setting = db.query(AppSetting).filter(AppSetting.key == SNAPSHOT_KEY).first()
        if setting:
            setting.value = json.dumps(snapshot)
            setting.updated_at = datetime.utcnow()
        else:
            setting = AppSetting(key=SNAPSHOT_KEY, value=json.dumps(snapshot))
            db.add(setting)
        db.commit()

        logger.info(f"Trending snapshot saved: {len(clusters)} clusters")
        return snapshot

    except Exception as e:
        logger.error(f"refresh_trending_snapshot failed: {e}")
        return {}
    finally:
        db.close()


def get_trending_snapshot() -> dict:
    """Load the latest snapshot from DB. Returns empty dict if none yet."""
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter(AppSetting.key == SNAPSHOT_KEY).first()
        if setting and setting.value:
            return json.loads(setting.value)
        return {}
    except Exception:
        return {}
    finally:
        db.close()

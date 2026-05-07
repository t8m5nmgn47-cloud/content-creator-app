"""
Content Filter — topic-based blocklist applied before any story is saved or posted.
Each category maps to a list of keywords checked against the article title (lowercase).
Blocked categories are stored in AppSetting as a comma-separated string.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SETTING_KEY = "blocked_categories"

# Each key is the display name shown in Settings.
# Keywords are matched against the article title (case-insensitive, substring match).
TOPIC_CATEGORIES: dict[str, dict] = {
    "Politics": {
        "description": "Elections, politicians, parties, legislation, government policy",
        "keywords": [
            "democrat", "republican", "gop", "congress", "senate", "election",
            "president", "white house", "governor", "ballot", "campaign",
            "partisan", "lobbyist", "dnc", "rnc", "legislation", "lawmaker",
            "mayor", "vote", "voter", "polling", "poll shows", "midterm",
            "political party", "left-wing", "right-wing", "progressive",
            "conservative", "liberal ", "maga", "inauguration",
        ],
    },
    "Religion": {
        "description": "Churches, religious figures, faith communities, theology",
        "keywords": [
            "church", "christian", "muslim", "islam", "islamic", "hindu",
            "buddhist", "catholic", "pope", "mosque", "temple", "faith",
            "prayer", "bible", "quran", "synagogue", "rabbi", "pastor",
            "sermon", "evangelical", "diocese", "religious", "worship",
            "salvation", "holy", "clergy", "nun ", "monk ", "archbishop",
        ],
    },
    "Crime & Violence": {
        "description": "Murders, shootings, arrests, trials, criminal cases",
        "keywords": [
            "murder", "shooting", "stabbing", "assault", "robbery", "arrested",
            "convicted", "sentenced", "prison", "homicide", "kidnap", "rape",
            "domestic violence", "mass shooting", "gunman", "hostage", "crime",
            "criminal", "inmate", "execution", "death row", "shooting suspect",
            "charged with", "indicted", "guilty", "acquitted",
        ],
    },
    "Celebrity Gossip": {
        "description": "Celebrity relationships, divorces, feuds, personal drama",
        "keywords": [
            "celebrity", "celebrities", "breakup", "divorce", "affair",
            "dating rumor", "splits from", "relationship", "pregnant with",
            "baby bump", "red carpet", "feud", "cheating", "kardashian",
            "taylor swift", "beyoncé", "drake", "engagement ring",
            "wedding plans", "hollywood drama",
        ],
    },
    "Sports": {
        "description": "Game results, player trades, sports leagues and tournaments",
        "keywords": [
            "nfl", "nba", "mlb", "nhl", "premier league", "champions league",
            "super bowl", "world series", "stanley cup", "nba finals",
            "trade deadline", "free agent", "touchdown", "home run",
            "quarterback", "head coach", "playoffs", "standings", "roster",
            "draft pick", "transfer fee",
        ],
    },
    "War & Conflict": {
        "description": "Armed conflict, military operations, casualties, war zones",
        "keywords": [
            "airstrike", "air strike", "bombing", "missile strike", "troops",
            "soldiers killed", "casualties", "civilian deaths", "ceasefire",
            "invasion", "offensive", "frontline", "drone strike", "war crime",
            "war in ", "conflict zone", "peacekeeping", "nato troops",
            "military operation",
        ],
    },
}


def get_blocked_categories(db) -> list[str]:
    """Read the list of blocked category names from AppSetting."""
    from app.models import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if not row or not row.value.strip():
        return []
    return [c.strip() for c in row.value.split(",") if c.strip()]


def save_blocked_categories(db, categories: list[str]):
    """Persist the blocked category list to AppSetting."""
    from datetime import datetime
    from app.models import AppSetting
    value = ",".join(categories)
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    db.commit()


def is_blocked(title: str, blocked_categories: list[str]) -> bool:
    """Return True if the title matches any keyword in any blocked category."""
    if not blocked_categories or not title:
        return False
    title_lower = title.lower()
    for cat_name in blocked_categories:
        cat = TOPIC_CATEGORIES.get(cat_name)
        if not cat:
            continue
        for kw in cat["keywords"]:
            if kw in title_lower:
                logger.debug(f"Blocked [{cat_name}] — keyword '{kw}' in: {title[:80]}")
                return True
    return False

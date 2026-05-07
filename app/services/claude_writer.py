"""
Claude Writer — uses Anthropic Claude to generate platform-specific captions,
hashtags, hooks, and viral scores for news items.
"""
import json
import logging
from datetime import datetime, timedelta

import anthropic

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppLog, NewsItem, Post

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def generate_twitter_post(title: str, description: str = "") -> dict:
    """
    Ask Claude to generate a Twitter/X post from a news headline.
    Returns a dict with: caption, hashtags, hook, viral_score, niche
    """
    client = _get_client()

    prompt = f"""You are a 50-year-old dad explaining today's news at the dinner table. You grew up in the 80s, lived through the 90s and 2000s, and you have an analogy for everything. You're not trying to be funny — you just are, because you explain everything through things that made sense back then.

Headline: {title}
Details: {description[:300] if description else 'N/A'}

Respond with ONLY valid JSON:
{{
  "caption": "your tweet here",
  "hashtags": ["hashtag1", "hashtag2"],
  "hook": "the opening line",
  "viral_score": 7,
  "niche": "Technology"
}}

Your voice:
- Connect the story to something from the 90s or 2000s that everyone remembers: Blockbuster, AOL dialup, Napster, MySpace, Tamagotchis, Y2K, the Motorola Razr, AIM away messages, Limewire, Circuit City, RadioShack, Kazaa, burning CDs, the Nokia 3310, Encarta encyclopedia, Ask Jeeves, MapQuest printing directions, frosted tips, cargo shorts, etc.
- Structure: explain what's happening now, then hit them with the analogy. Short and confident.
- Matter-of-fact tone. You've seen this before. You're not impressed.
- Slightly confused by modern things but you've figured out the equivalent
- Examples of the vibe:
  "So AI is doing your homework now. We had Cliff Notes. Same thing, different font."
  "They shut down the crypto exchange and everyone lost their money. We called that a bank in 2008."
  "Apple is charging $20/month for features that used to be free. Blockbuster late fees had more integrity."
- Max 240 chars
- No hashtags in the caption
- 1 emoji max, only if your dad-self would actually use it

viral_score: 1-10 engagement likelihood
niche: Technology, Business, Entertainment, Health, Science, Politics, Sports, Finance, AI, or Other"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code blocks if Claude adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    # Ensure hashtags don't have # prefix (we add it in templates)
    result["hashtags"] = [
        h.lstrip("#") for h in result.get("hashtags", [])
    ]

    return result


def generate_posts_for_queue():
    """
    Main entry point — called by the scheduler every 3 hours.
    Finds unprocessed news items and generates Twitter posts for the best ones.
    """
    db = SessionLocal()
    try:
        # Get unprocessed news items, newest first
        items = (
            db.query(NewsItem)
            .filter(NewsItem.processed == False)
            .order_by(NewsItem.fetched_at.desc())
            .limit(20)
            .all()
        )

        if not items:
            logger.info("No unprocessed news items found — skipping generation")
            return 0

        logger.info(f"Generating posts for {len(items)} news items...")
        generated = 0
        skipped = 0

        for item in items:
            try:
                result = generate_twitter_post(item.title, item.description)

                viral_score = float(result.get("viral_score", 5))

                # Update the news item
                item.viral_score = viral_score
                item.processed = True

                # Only queue posts with a decent viral score (5+)
                if viral_score >= 5:
                    # Schedule for a future time slot
                    scheduled = _next_schedule_slot(db)

                    status = "approved" if settings.auto_approve_posts else "pending"

                    post = Post(
                        news_item_id=item.id,
                        platform="twitter",
                        caption=result.get("caption", ""),
                        hashtags=", ".join(result.get("hashtags", [])),
                        hook=result.get("hook", ""),
                        status=status,
                        scheduled_for=scheduled,
                    )
                    db.add(post)
                    generated += 1
                else:
                    logger.info(f"Skipped low-score item (score={viral_score}): {item.title[:60]}")
                    skipped += 1

                db.commit()

            except json.JSONDecodeError as e:
                logger.error(f"Claude returned invalid JSON for item {item.id}: {e}")
                item.processed = True
                db.commit()
            except Exception as e:
                logger.error(f"Failed to generate post for item {item.id}: {e}")
                db.rollback()

        log_entry = AppLog(
            level="info",
            job="claude_writer",
            message=f"Generated {generated} posts, skipped {skipped} low-score items",
        )
        db.add(log_entry)
        db.commit()

        logger.info(f"Caption generation complete: {generated} posts queued")
        return generated

    except Exception as e:
        logger.error(f"generate_posts_for_queue failed: {e}")
        try:
            db.add(AppLog(level="error", job="claude_writer", message=str(e)))
            db.commit()
        except Exception:
            pass
        return 0
    finally:
        db.close()


def generate_post_from_trend(
    topic: str,
    summary: str,
    hook: str,
    best_angle: str,
    tone_playful: int = 3,
    tone_energy: int = 3,
    tone_casual: int = 3,
) -> dict:
    """
    Generate 3 Twitter post variations from a trending story cluster.
    Tone sliders are 1-5: playful (1=serious, 5=playful), energy (1=calm, 5=fired up),
    casual (1=formal, 5=very casual).
    Returns {"variations": [{caption, hashtags, tone}, ...], "viral_score", "niche"}
    """
    client = _get_client()

    tone_playful = max(1, min(5, int(tone_playful)))
    tone_energy = max(1, min(5, int(tone_energy)))
    tone_casual = max(1, min(5, int(tone_casual)))

    playful_desc = ["very serious and factual", "mostly serious", "balanced", "somewhat playful and fun", "very playful and witty"][tone_playful - 1]
    energy_desc = ["very calm and measured", "low-key", "moderate energy", "energetic and enthusiastic", "fired up and intense"][tone_energy - 1]
    casual_desc = ["formal, proper grammar", "mostly formal", "conversational", "casual and relaxed", "very casual — fragments, lowercase fine, ellipses ok"][tone_casual - 1]

    prompt = f"""You are a comedian writing tweets about trending news. Make people actually laugh. Think absurdist Twitter, dry wit, unexpected angles — the kind of tweet that gets screenshot and shared.

Topic: {topic}
What's happening: {summary}
Angle to use: {best_angle}
Suggested hook: {hook}

Tone settings (apply to ALL 3 variations):
- Mood: {playful_desc}
- Energy: {energy_desc}
- Style: {casual_desc}

Write 3 variations, each using a different comedy style:
1. "casual" — absurdist or deadpan, like texting a friend the most ridiculous take on this story
2. "hot take" — exaggerated reaction, treat this like the most dramatic or most mundane thing ever (whichever is funnier), strong opinion
3. "question" — start with a weird angle or observation that makes people go "wait... yeah actually" before they laugh

Respond with ONLY valid JSON:
{{
  "variations": [
    {{
      "tone": "casual",
      "caption": "tweet text, max 240 chars",
      "hashtags": ["tag1", "tag2"]
    }},
    {{
      "tone": "hot take",
      "caption": "tweet text, max 240 chars",
      "hashtags": ["tag1", "tag2"]
    }},
    {{
      "tone": "question",
      "caption": "tweet text, max 240 chars",
      "hashtags": ["tag1", "tag2"]
    }}
  ],
  "viral_score": 8,
  "niche": "Technology"
}}

Rules for all 3:
- Actually funny > technically accurate. Commit to the joke.
- Apply the tone settings — they shape HOW funny, not whether to be funny
- Lowercase, fragments, ellipses all fine if they help the comedic timing
- Emojis only if they're part of the joke (💀 🫠 😭 are comedy gold)
- Max 240 chars per caption, no hashtags inside caption
- Roast the situation/irony, never punch at real individuals"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    for v in result.get("variations", []):
        v["hashtags"] = [h.lstrip("#") for h in v.get("hashtags", [])]
    return result


def suggest_niches() -> list[dict]:
    """
    Ask Claude Sonnet to suggest trending content niches based on current news.
    Used by the /niches page "Ask Claude" button.
    """
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": """Suggest 5 trending content niches that would perform well on social media right now in 2025.
For each niche, explain why it's trending and what keywords to monitor.

Respond with ONLY valid JSON:
[
  {
    "name": "Niche Name",
    "description": "Why this niche is trending and what kind of content to create",
    "keywords": "keyword1, keyword2, keyword3, keyword4"
  }
]"""
        }],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def generate_videos_for_queue():
    """
    Generate Runway videos for top approved posts (viral_score >= 8) that
    don't have a video yet. Called by the scheduler 5 min after post generation.
    """
    if not settings.runway_api_key:
        logger.info("RUNWAY_API_KEY not set — skipping video generation")
        return 0

    from app.services.runway_client import generate_video, build_video_prompt

    db = SessionLocal()
    try:
        posts = (
            db.query(Post)
            .join(NewsItem, Post.news_item_id == NewsItem.id)
            .filter(Post.status == "approved")
            .filter(Post.video_url == "")
            .filter(NewsItem.viral_score >= 8)
            .order_by(NewsItem.viral_score.desc())
            .limit(3)
            .all()
        )

        if not posts:
            logger.info("No high-score posts need video generation this cycle")
            return 0

        generated = 0
        for post in posts:
            item = db.query(NewsItem).filter(NewsItem.id == post.news_item_id).first()
            if not item:
                continue
            prompt = build_video_prompt(item.title, item.description)
            video_url = generate_video(prompt)
            if video_url:
                post.video_url = video_url
                db.commit()
                logger.info(f"Video ready for post {post.id}")
                generated += 1
            else:
                logger.warning(f"Video generation failed for post {post.id}")

        db.add(AppLog(
            level="info",
            job="runway",
            message=f"Generated {generated} videos for queue",
        ))
        db.commit()
        return generated

    except Exception as e:
        logger.error(f"generate_videos_for_queue failed: {e}")
        return 0
    finally:
        db.close()


def _next_schedule_slot(db) -> datetime:
    """
    Find the next available posting slot.
    Ensures posts are spread out — at least 1 hour apart.
    """
    now = datetime.utcnow()
    # Check the latest scheduled post
    latest_post = (
        db.query(Post)
        .filter(Post.status.in_(["pending", "approved"]))
        .filter(Post.scheduled_for > now)
        .order_by(Post.scheduled_for.desc())
        .first()
    )

    if latest_post and latest_post.scheduled_for:
        # Schedule at least 1 hour after the last queued post
        return latest_post.scheduled_for + timedelta(hours=1)
    else:
        # Nothing in queue — schedule 30 minutes from now
        return now + timedelta(minutes=30)

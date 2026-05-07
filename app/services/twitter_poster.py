"""
Twitter Poster — posts to X/Twitter using Tweepy.
Picks the next approved post from the queue and sends it.
"""
import json
import logging
from datetime import datetime

import tweepy

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppLog, Post

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=settings.twitter_api_key,
        consumer_secret=settings.twitter_api_secret,
        access_token=settings.twitter_access_token,
        access_token_secret=settings.twitter_access_secret,
        bearer_token=settings.twitter_bearer_token,
    )


def _build_tweet_text(post: Post) -> str:
    """Combine caption and hashtags into final tweet text."""
    caption = post.caption or ""
    hashtags = ""
    if post.hashtags:
        tags = [f"#{h.strip()}" for h in post.hashtags.split(",") if h.strip()]
        hashtags = " ".join(tags)

    # Twitter limit is 280 chars
    if hashtags:
        full_text = f"{caption}\n\n{hashtags}"
        if len(full_text) <= 280:
            return full_text
        # If too long, trim hashtags
        return caption[:277] + "..."
    return caption[:280]


def post_tweet(post_id: int) -> bool:
    """
    Post a specific post (by DB id) to Twitter.
    Returns True on success, False on failure.
    """
    db = SessionLocal()
    post = None
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            logger.error(f"Post {post_id} not found")
            return False

        if post.status == "posted":
            logger.warning(f"Post {post_id} already posted — skipping")
            return False

        tweet_text = _build_tweet_text(post)
        client = _get_client()

        response = client.create_tweet(text=tweet_text)
        tweet_id = response.data["id"]

        post.status = "posted"
        post.posted_at = datetime.utcnow()
        post.platform_post_id = str(tweet_id)
        post.error_message = ""

        db.add(AppLog(
            level="info",
            job="twitter_poster",
            message=f"Posted tweet ID {tweet_id}",
            details=json.dumps({"post_id": post_id, "tweet_id": tweet_id}),
        ))
        db.commit()

        logger.info(f"✅ Posted tweet {tweet_id} for post {post_id}")
        return True

    except tweepy.TooManyRequests as e:
        logger.warning(f"Twitter rate limit hit for post {post_id} — will retry next slot")
        if post:
            post.error_message = "Rate limit — will retry"
            db.commit()
        return False

    except tweepy.Forbidden as e:
        logger.error(f"Twitter forbidden error for post {post_id}: {e}")
        if post:
            post.status = "failed"
            post.error_message = f"Forbidden: {str(e)}"
            db.commit()
        return False

    except Exception as e:
        logger.error(f"Failed to post tweet for post {post_id}: {e}")
        if post:
            try:
                post.status = "failed"
                post.error_message = str(e)[:500]
                db.add(AppLog(
                    level="error",
                    job="twitter_poster",
                    message=f"Failed to post: {str(e)}",
                    details=json.dumps({"post_id": post_id}),
                ))
                db.commit()
            except Exception:
                db.rollback()
        return False
    finally:
        db.close()


def post_next_in_queue() -> bool:
    """
    Called by the scheduler at each posting time.
    Picks the next approved Twitter post and sends it.
    """
    db = SessionLocal()
    try:
        # Find the next approved post that's due
        post = (
            db.query(Post)
            .filter(Post.platform == "twitter")
            .filter(Post.status == "approved")
            .order_by(Post.scheduled_for.asc())
            .first()
        )

        if not post:
            logger.info("No approved Twitter posts in queue — skipping this slot")
            db.add(AppLog(
                level="info",
                job="twitter_poster",
                message="No posts in queue for this time slot",
            ))
            db.commit()
            return False

        return post_tweet(post.id)

    except Exception as e:
        logger.error(f"post_next_in_queue failed: {e}")
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass

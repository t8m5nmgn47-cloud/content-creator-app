"""
Runway Gen-3 video generation client.
Sends a text prompt, polls until complete, returns the video URL.
"""
import logging
import time
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"


def generate_video(prompt: str, duration: int = 5) -> str | None:
    """
    Generate a short video from a text prompt using Runway Gen-4.
    Returns the video URL on success, None on failure.
    Duration: 5 or 10 seconds.
    """
    if not settings.runway_api_key:
        logger.warning("RUNWAY_API_KEY not set — skipping video generation")
        return None

    headers = {
        "Authorization": f"Bearer {settings.runway_api_key}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }

    # Step 1 — Submit the generation request
    payload = {
        "promptText": prompt[:500],
        "model": "gen4.5",
        "duration": duration,
        "ratio": "1280:720",   # landscape — correct ratio for gen4.5
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{RUNWAY_API_BASE}/text_to_video",   # text-to-video endpoint
                headers=headers,
                json=payload,
            )

            if response.status_code not in (200, 201):
                error_body = response.text[:300]
                if "credits" in error_body.lower():
                    logger.error("Runway: Not enough credits — add credits at app.runwayml.com")
                else:
                    logger.error(f"Runway submit failed: {response.status_code} — {error_body}")
                return None

            task_id = response.json().get("id")
            if not task_id:
                logger.error(f"Runway returned no task ID: {response.text[:200]}")
                return None

            logger.info(f"Runway task submitted: {task_id}")

        # Step 2 — Poll until done (max 3 minutes)
        return _poll_for_result(task_id, headers)

    except Exception as e:
        logger.error(f"Runway video generation failed: {e}")
        return None


def _poll_for_result(task_id: str, headers: dict, max_wait: int = 180) -> str | None:
    """Poll the Runway task until it succeeds or fails."""
    elapsed = 0
    interval = 5

    with httpx.Client(timeout=30) as client:
        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval

            try:
                response = client.get(
                    f"{RUNWAY_API_BASE}/tasks/{task_id}",
                    headers=headers,
                )
                data = response.json()
                status = data.get("status", "")

                if status == "SUCCEEDED":
                    output = data.get("output", [])
                    video_url = output[0] if output else None
                    logger.info(f"Runway task {task_id} succeeded: {video_url}")
                    return video_url

                elif status == "FAILED":
                    logger.error(f"Runway task {task_id} failed: {data.get('failure', '')}")
                    return None

                else:
                    logger.info(f"Runway task {task_id} status: {status} ({elapsed}s elapsed)")

            except Exception as e:
                logger.error(f"Runway poll error: {e}")

    logger.error(f"Runway task {task_id} timed out after {max_wait}s")
    return None


def build_video_prompt(title: str, description: str = "") -> str:
    """Turn a news headline into a cinematic video prompt."""
    base = title.strip()
    if description:
        base += f". {description[:150].strip()}"

    return (
        f"Cinematic news-style video: {base}. "
        "Professional broadcast quality, dynamic camera movement, "
        "dramatic lighting, 4K ultra HD, photorealistic."
    )

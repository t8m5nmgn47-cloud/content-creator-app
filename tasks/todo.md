# Content Creator App — Master Plan

## Project Summary
An automated content creation and social media posting system that:
- Monitors the internet for breaking news and trending topics
- Uses Claude AI to suggest/manage content niches and write captions
- Uses Runway Gen-3 to generate videos
- Posts 8+ times/day across all major social platforms
- Runs 24/7 in the cloud on Railway

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Dashboard (Web UI)                │
│         Configure niches, approve content,          │
│           view schedule, monitor posts              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  Core App (Python/FastAPI)           │
├─────────────────┬───────────────┬───────────────────┤
│ Content Engine  │ Video Engine  │  Scheduler        │
│  (Claude API)   │ (Runway Gen-3)│  (Celery+Redis)   │
├─────────────────┴───────────────┴───────────────────┤
│                 News Sources                        │
│    NewsAPI · Reddit API · RSS Feeds                 │
├─────────────────────────────────────────────────────┤
│              Social Publishers                      │
│  Twitter · LinkedIn · Facebook · Instagram ·        │
│  TikTok · YouTube · Threads · Pinterest             │
├─────────────────────────────────────────────────────┤
│              Database (PostgreSQL)                  │
│   Posts · Schedules · Niches · Analytics            │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack
| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.11 | Best ecosystem for APIs + scraping |
| Web UI | FastAPI + Jinja2 | Lightweight, fast dashboard |
| Task Queue | Celery + Redis | Reliable scheduled/async posting |
| Database | PostgreSQL | Stores all posts, schedules, configs |
| ORM | SQLAlchemy | Easy database management |
| AI Content | Anthropic Claude API | Niche discovery + caption writing |
| AI Video | Runway Gen-3 API | Video generation |
| News | NewsAPI + PRAW + RSS | Breaking news sources |
| Hosting | Railway | 24/7 cloud, easy deploy |
| Code Storage | GitHub | Version control + Railway integration |

---

## Social Media Libraries
| Platform | Library |
|----------|---------|
| X/Twitter | tweepy |
| LinkedIn | linkedin-api |
| Facebook | facebook-sdk (Meta Graph API) |
| Instagram | Meta Graph API |
| TikTok | TikTok API for Developers |
| YouTube | google-api-python-client |
| Threads | Meta Graph API (same as Instagram) |
| Pinterest | pinterest-api-python |

---

## Phase 1 — Setup & Accounts (User Action Required)
- [ ] Create GitHub account (github.com)
- [ ] Create Railway account (railway.app) and connect to GitHub
- [ ] Create Anthropic account (console.anthropic.com) — get API key
- [ ] Create Runway Gen-3 account (runwayml.com) — get API key
- [ ] Create NewsAPI account (newsapi.org) — get API key
- [ ] Create Reddit developer account (reddit.com/prefs/apps) — get API key
- [ ] Create X/Twitter developer account (developer.twitter.com)
- [ ] Create LinkedIn developer account (linkedin.com/developers)
- [ ] Create Meta developer account (developers.facebook.com) — covers Facebook, Instagram, Threads
- [ ] Create TikTok developer account (developers.tiktok.com)
- [ ] Create Google Cloud account (console.cloud.google.com) — for YouTube API
- [ ] Create Pinterest developer account (developers.pinterest.com)

## Phase 2 — Project Scaffold
- [ ] Initialize project structure and GitHub repo
- [ ] Set up Python environment and dependencies
- [ ] Configure environment variables (.env file)
- [ ] Set up PostgreSQL database schema
- [ ] Set up Redis for task queue
- [ ] Build basic FastAPI app with dashboard skeleton

## Phase 3 — Content Discovery Engine
- [ ] Integrate NewsAPI for breaking news
- [ ] Integrate Reddit API (PRAW) for trending topics
- [ ] Build RSS feed monitor for custom sources
- [ ] Build Claude AI niche suggester (auto-suggest content categories)
- [ ] Build manual niche input (user can add their own topics)
- [ ] Build content scoring system (rank stories by virality potential)

## Phase 4 — Content Generation
- [ ] Build Claude caption writer (platform-aware — different style per platform)
- [ ] Build hashtag generator
- [ ] Build hook/headline writer
- [ ] Integrate Runway Gen-3 API for video generation
- [ ] Build image-to-video and text-to-video pipelines
- [ ] Build content approval queue (optional manual review before posting)

## Phase 5 — Social Media Publishers
- [ ] Build X/Twitter publisher
- [ ] Build LinkedIn publisher
- [ ] Build Facebook publisher
- [ ] Build Instagram publisher (video + carousel)
- [ ] Build TikTok publisher
- [ ] Build YouTube Shorts publisher
- [ ] Build Threads publisher
- [ ] Build Pinterest publisher

## Phase 6 — Scheduler
- [ ] Build Celery task queue with Redis
- [ ] Build posting schedule (8+ posts/day, spread across platforms)
- [ ] Build peak-time optimizer (post when audiences are most active)
- [ ] Build retry logic (if a post fails, retry automatically)
- [ ] Build rate limit handler (stay within each platform's limits)

## Phase 7 — Dashboard UI
- [ ] Build main dashboard (post queue, recent posts, stats)
- [ ] Build niche manager (add/remove/edit content topics)
- [ ] Build schedule viewer (see upcoming posts)
- [ ] Build platform toggle (enable/disable platforms)
- [ ] Build analytics page (engagement, post counts)
- [ ] Build API key manager (connect/reconnect social accounts)

## Phase 8 — Railway Deployment
- [ ] Create Dockerfile
- [ ] Configure Railway environment variables
- [ ] Deploy PostgreSQL on Railway
- [ ] Deploy Redis on Railway
- [ ] Deploy main app on Railway
- [ ] Set up custom domain (optional)
- [ ] Verify all services running and posting correctly

---

## Monthly Cost Estimate
| Service | Cost |
|---------|------|
| Anthropic Claude API | ~$20 |
| Runway Gen-3 | ~$15 |
| Railway hosting | ~$10 |
| NewsAPI (free tier to start) | $0 |
| Everything else | $0 |
| **Total** | **~$45/mo** |

---

## Review
_To be filled in after completion_

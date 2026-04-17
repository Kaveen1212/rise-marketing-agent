"""
app/main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI application entry point for the RISE Tech Village Poster Design Agent.

What this file does:
  1. Creates the FastAPI app with lifespan (startup + shutdown logic)
  2. Adds CORS middleware so the Next.js frontend can talk to this API
  3. Registers all API routers under the /poster prefix
  4. Starts the APScheduler background jobs on startup
  5. Verifies the database connection before accepting traffic
  6. Adds a /health endpoint for load balancer checks

Run locally:
  uvicorn app.main:app --reload --port 8000
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import check_database_connection
from app.services.publish_service import collect_due_analytics, publish_due_posts

log = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Scheduler — runs background jobs inside the same async event loop as FastAPI
# ─────────────────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — code that runs on startup and shutdown
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Everything BEFORE yield runs on startup.
    Everything AFTER yield runs on shutdown.

    This replaces the old @app.on_event("startup") pattern.
    """

    # ── Startup ───────────────────────────────────────────────────────────────
    log.info("rise_poster_agent_starting", version=settings.APP_VERSION, env=settings.APP_ENV)

    # 1. Verify the database is reachable before accepting any traffic.
    #    If the DB is down, the app refuses to start rather than serving errors.
    db_ok = await check_database_connection()
    if not db_ok:
        log.error("startup_failed_db_unreachable")
        raise RuntimeError("Database unreachable at startup — refusing to start.")

    log.info("database_connection_verified")

    # 2. Register background jobs
    #    publish_due_posts:     every 60 seconds — push scheduled posts to platforms
    #    collect_due_analytics: every 5 minutes  — fetch 24h stats from platform APIs
    scheduler.add_job(
        publish_due_posts,
        trigger="interval",
        seconds=60,
        id="publish_due_posts",
        replace_existing=True,
        max_instances=1,        # prevent overlap if a run takes > 60s
    )
    scheduler.add_job(
        collect_due_analytics,
        trigger="interval",
        minutes=5,
        id="collect_due_analytics",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    log.info("scheduler_started", jobs=["publish_due_posts", "collect_due_analytics"])

    yield  # ← app is now running and serving requests

    # ── Shutdown ──────────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    log.info("scheduler_stopped")
    log.info("rise_poster_agent_stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RISE Tech Village — Poster Design Agent",
    description=(
        "Human-in-the-Loop AI system that generates, quality-checks, "
        "and publishes social media poster content for RISE Tech Village, Sri Lanka."
    ),
    version=settings.APP_VERSION,
    # Disable /docs and /redoc in production — no public API exploration
    docs_url="/docs" if not settings.is_production() else None,
    redoc_url="/redoc" if not settings.is_production() else None,
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# CORS — allow the Next.js review interface to call this API
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Routers — each file in app/api/ owns one area of the spec
# ─────────────────────────────────────────────────────────────────────────────
#
# All routes are prefixed with /poster to match spec §5.1:
#   Base URL: https://api.risetechvillage.lk/v1/poster
#
# Import routers here once they are implemented.
# They are commented out now so the app still starts while stubs are empty.

from pathlib import Path
from fastapi.staticfiles import StaticFiles

from app.api.analytics import router as analytics_router
from app.api.briefs    import router as briefs_router
from app.api.chat      import router as chat_router
from app.api.images    import router as images_router
from app.api.review    import router as review_router

# ─────────────────────────────────────────────────────────────────────────────
# Local storage — serve poster images from disk in development
# ─────────────────────────────────────────────────────────────────────────────
storage_path = Path("storage")
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_path)), name="storage")

app.include_router(briefs_router,    prefix="/poster", tags=["Briefs"])
app.include_router(review_router,    prefix="/poster", tags=["Review"])
app.include_router(analytics_router, prefix="/poster", tags=["Analytics"])
app.include_router(chat_router,      prefix="/poster", tags=["Chat"])
app.include_router(images_router,    prefix="/poster", tags=["Images"])


# ─────────────────────────────────────────────────────────────────────────────
# Health check — called by load balancer / Docker healthcheck every 30s
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """
    Returns 200 if the app is running and the database is reachable.
    Returns 503 if the database is down.

    Used by:
      - AWS ECS health check
      - Docker HEALTHCHECK instruction
      - Uptime monitoring (Grafana)
    """
    db_ok = await check_database_connection()
    if not db_ok:
        from fastapi import Response
        return Response(
            content='{"status":"unhealthy","db":false}',
            status_code=503,
            media_type="application/json",
        )
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "db": True,
        "scheduler_running": scheduler.running,
    }

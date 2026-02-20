"""
FastAPI application entry point.

Responsibilities:
- Create FastAPI app
- Register routers
- Provide health checks
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings

from app.api.auth import router as auth_router
from app.api import subscriptions
from app.api.social_accounts import router as social_accounts_router
from app.api.groups import router as groups_router
from app.api.posts import router as posts_router
from app.api.media import router as media_router
from app.api.payments import router as payments_router
from app.api.proxies import router as proxies_router
from app.api.admin import router as admin_router
from app.api.clips import router as clips_router
from app.api.analytics import router as analytics_router
from app.api.youtube_analytics import router as yt_router
from app.services.database import init_db
from app.services.auth_database import init_auth_db
from app.api.messages import router as messages_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
    )

    # ✅ CORS
    cors_origins = [
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # =========================================================
    # STATIC MEDIA (REQUIRED FOR CLIPS)
    # =========================================================
    # Mount the entire media root at /media
    app.mount(
        "/media",
        StaticFiles(directory=settings.MEDIA_ROOT),
        name="media",
    )

    # =========================================================
    # ROUTERS
    # =========================================================
    app.include_router(auth_router)
    app.include_router(groups_router)
    app.include_router(social_accounts_router)
    app.include_router(posts_router)
    app.include_router(media_router)
    app.include_router(payments_router)
    app.include_router(proxies_router)
    app.include_router(admin_router)
    app.include_router(
        subscriptions.router,
        prefix="",
        tags=["subscriptions"],
    )
    app.include_router(clips_router)
    app.include_router(analytics_router)
    app.include_router(yt_router)
    app.include_router(messages_router)

    # =========================================================
    # HEALTH CHECK
    # =========================================================
    @app.get("/", tags=["health"])
    def health_check():
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "environment": settings.ENV,
        }

    # =========================================================
    # STARTUP
    # =========================================================
    @app.on_event("startup")
    def startup():
        init_db()
        init_auth_db()

    return app


app = create_app()
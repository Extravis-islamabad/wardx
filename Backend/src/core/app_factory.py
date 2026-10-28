"""Builds the FastAPI app and runs startup: migrations, vault unseal, first admin, scheduler."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import Settings, get_settings, resolve_jwt_secret, resolve_vault_kek
from src.core.db import dispose_engine, init_engine, session_factory
from src.core.migration_runner import run_migrations
from src.errors.handlers import register_exception_handlers
from src.routers.v1 import auth, dashboard, directory, health, users
from src.routers.v1.access import checkouts, requests
from src.routers.v1.audit import audit_events
from src.routers.v1.inventory import accounts, targets
from src.routers.v1.sessions import command_rules, gateway, sessions
from src.scheduler.jobs import build_scheduler
from src.services import user_service, vault_service
from src.vault.envelope import Keyring

logger = structlog.get_logger(__name__)


async def startup(settings: Settings) -> None:
    # Fail fast on missing keys before touching the database.
    resolve_jwt_secret(settings)
    vault_service.set_keyring(
        Keyring.from_base64(resolve_vault_kek(settings), settings.vault_kek_retired)
    )
    engine = init_engine(settings.database_url, settings.db_pool_size)
    await run_migrations(engine)
    async with session_factory()() as session:
        await user_service.bootstrap_admin(session, settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await startup(settings)
        scheduler = None
        if settings.runs_scheduler():
            scheduler = build_scheduler(settings)
            scheduler.start()
        logger.info("wardx_started", role=settings.app_role, environment=settings.environment)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            await dispose_engine()

    app = FastAPI(
        title="WardX API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    register_exception_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def liveness() -> dict:
        return {"status": "ok"}

    for module in (
        health,
        auth,
        users,
        targets,
        accounts,
        requests,
        checkouts,
        audit_events,
        dashboard,
        gateway,
        sessions,
        command_rules,
        directory,
    ):
        app.include_router(module.router, prefix="/api/v1")
    return app

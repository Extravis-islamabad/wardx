"""Entry point: ``uvicorn main:app`` (API), or ``python main.py`` for the other roles.

WARDX_APP_ROLE=scheduler runs the workers, WARDX_APP_ROLE=gateway the SSH session gateway.
"""

from __future__ import annotations

import asyncio
import signal

from src.core.app_factory import create_app, startup
from src.core.config import get_settings
from src.core.db import dispose_engine

settings = get_settings()
app = create_app(settings) if settings.runs_api() else None


async def run_scheduler_only() -> None:
    from src.scheduler.jobs import build_scheduler
    from src.scheduler.leader import LeaderElector

    await startup(settings)
    elector = LeaderElector(settings)
    elector.start()
    scheduler = build_scheduler(settings, elector)
    scheduler.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    scheduler.shutdown(wait=False)
    await elector.stop()
    await dispose_engine()


if __name__ == "__main__":
    if settings.app_role == "scheduler":
        asyncio.run(run_scheduler_only())
    elif settings.app_role == "gateway":
        from src.gateway.server import run_gateway

        asyncio.run(run_gateway(settings))
    else:
        import uvicorn

        import os

        port = int(os.environ.get("WARDX_API_PORT", "8000"))
        uvicorn.run("main:app", host="0.0.0.0", port=port)  # noqa: S104

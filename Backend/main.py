"""Entry point: ``uvicorn main:app`` (API) or ``python main.py`` with WARDX_APP_ROLE=scheduler."""

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

    await startup(settings)
    scheduler = build_scheduler(settings)
    scheduler.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    scheduler.shutdown(wait=False)
    await dispose_engine()


if __name__ == "__main__":
    if settings.app_role == "scheduler":
        asyncio.run(run_scheduler_only())
    else:
        import uvicorn

        uvicorn.run("main:app", host="0.0.0.0", port=8000)  # noqa: S104

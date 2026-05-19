"""Vector sync scheduler.

Registers a cron or interval job on the shared APScheduler instance
from ``app.infrastructure.scheduler``.
"""

from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.config import settings
from app.core.logging import get_logger
from app.infrastructure.scheduler import get_scheduler
from app.vector.sync import run_property_vector_sync

logger = get_logger(__name__)


def start_vector_sync_scheduler(app: FastAPI) -> None:
    """Register property vector sync job if enabled."""
    del app

    if not settings.VECTOR_SYNC_ENABLED:
        logger.info("Vector sync scheduler disabled via settings")
        return

    scheduler = get_scheduler()

    if settings.VECTOR_SYNC_CRON:
        trigger = CronTrigger.from_crontab(settings.VECTOR_SYNC_CRON)
        logger.info("Scheduling vector sync with CRON", extra={"cron": settings.VECTOR_SYNC_CRON})
    else:
        seconds = int(settings.VECTOR_SYNC_INTERVAL_SECONDS)
        trigger = IntervalTrigger(seconds=seconds)
        logger.info("Scheduling vector sync with interval", extra={"seconds": seconds})

    async def job_wrapper():
        try:
            stats = await run_property_vector_sync()
            logger.info("Vector sync pass completed", extra=stats)
        except Exception as e:  # noqa: BLE001
            logger.error("Vector sync job failed: %s", e)

    scheduler.add_job(
        job_wrapper,
        trigger,
        id="property_vector_sync",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Vector sync job registered")

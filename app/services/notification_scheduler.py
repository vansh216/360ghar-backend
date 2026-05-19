"""Notification scheduler.

Registers a daily marketing push job on the shared APScheduler instance
from ``app.infrastructure.scheduler``.
"""

from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.config import settings
from app.core.logging import get_logger
from app.infrastructure.scheduler import get_scheduler
from app.services.notifications import send_to_topic

logger = get_logger(__name__)


def start_notification_scheduler(app: FastAPI) -> None:
    """Register push-notification cron job if enabled in settings."""
    del app

    if not settings.ENABLE_NOTIF_SCHEDULER:
        logger.info("Notification scheduler disabled via settings")
        return

    scheduler = get_scheduler()

    async def _daily_marketing_job():
        try:
            await send_to_topic(
                topic="marketing",
                title="Good morning!",
                body="Check out new updates today.",
                data=None,
                deep_link=None,
                type_key="promotion_generic",
            )
            logger.info("Daily marketing push job executed")
        except Exception as e:
            logger.error("Daily marketing push job failed: %s", e, exc_info=True)

    scheduler.add_job(_daily_marketing_job, CronTrigger(hour=9, minute=0))
    logger.info("Notification scheduler job registered")

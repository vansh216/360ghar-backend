from __future__ import annotations

import pytest

import app.services.blog_auto_publish_scheduler as mod
from app.infrastructure import scheduler as scheduler_mod


class DummyScheduler:
    def __init__(self, timezone=None):
        self.jobs = []
        self.running = False
        self.timezone = timezone

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, "kwargs": kwargs})


def _trigger_timezone_name(trigger) -> str:
    timezone = getattr(trigger, "timezone", None)
    return getattr(timezone, "key", str(timezone))


@pytest.mark.asyncio
async def test_start_auto_blog_scheduler_is_disabled(monkeypatch):
    monkeypatch.setattr(mod.settings, "AUTO_BLOG_ENABLED", False)
    dummy = DummyScheduler()
    monkeypatch.setattr(scheduler_mod, "_scheduler", dummy)

    mod.start_auto_blog_scheduler(app=None)

    assert len(dummy.jobs) == 0


@pytest.mark.asyncio
async def test_start_auto_blog_scheduler_registers_daily_job(monkeypatch):
    monkeypatch.setattr(mod.settings, "AUTO_BLOG_ENABLED", True)
    monkeypatch.setattr(mod.settings, "AUTO_BLOG_CRON", "0 20 * * *")
    monkeypatch.setattr(mod.settings, "AUTO_BLOG_TIMEZONE", "Asia/Kolkata")
    dummy = DummyScheduler()
    monkeypatch.setattr(scheduler_mod, "_scheduler", dummy)

    mod.start_auto_blog_scheduler(app=None)

    assert len(dummy.jobs) == 1
    job = dummy.jobs[0]
    assert job["kwargs"]["id"] == "auto_blog_publish"
    assert job["kwargs"]["replace_existing"] is True
    assert job["kwargs"]["max_instances"] == 1
    assert job["kwargs"]["coalesce"] is True
    assert _trigger_timezone_name(job["trigger"]) == "Asia/Kolkata"
    assert "hour='20'" in str(job["trigger"])
    assert "minute='0'" in str(job["trigger"])

from __future__ import annotations

import asyncio

import pytest

from app.core.sse import SSEEventBus, SSESubscriberLimitError


@pytest.mark.asyncio
async def test_reap_removes_idle_queue_after_ttl() -> None:
    bus = SSEEventBus()
    bus._QUEUE_TTL_SECONDS = 0.01
    queue = await bus.subscribe(1)

    await asyncio.sleep(0.02)
    await bus._reap_dead_queues_async()

    assert queue.empty()
    assert bus._queues == {}


@pytest.mark.asyncio
async def test_reap_keeps_touched_long_lived_queue() -> None:
    bus = SSEEventBus()
    bus._QUEUE_TTL_SECONDS = 0.01
    queue = await bus.subscribe(1)

    await asyncio.sleep(0.02)
    await bus.touch(queue)
    await bus._reap_dead_queues_async()

    assert bus._queues == {1: [queue]}


@pytest.mark.asyncio
async def test_subscribe_rejects_when_global_cap_reached() -> None:
    bus = SSEEventBus()
    bus._MAX_GLOBAL_SUBSCRIBERS = 1

    await bus.subscribe(1)

    with pytest.raises(SSESubscriberLimitError):
        await bus.subscribe(2)

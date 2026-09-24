# SPDX-License-Identifier: AGPL-3.0-or-later
"""The UI bridge wakes for work instead of polling on a timer."""

import asyncio
import threading

from mouse_control.async_wake_queue import AsyncWakeQueue


def test_synchronous_producer_wakes_async_consumer_without_sleep(monkeypatch):
    async def forbidden_sleep(*_args, **_kwargs):
        raise AssertionError("event-driven queue must not poll with asyncio.sleep")

    monkeypatch.setattr(asyncio, "sleep", forbidden_sleep)
    work: AsyncWakeQueue[int] = AsyncWakeQueue()

    async def consume() -> list[int]:
        values = []
        for _ in range(3):
            values.append(await work.get())
            work.task_done()
        return values

    async def exercise() -> list[int]:
        loop = asyncio.get_running_loop()
        producer = threading.Thread(
            target=lambda: (work.put(1), work.put(2), work.put(3)),
            daemon=True,
        )
        loop.call_soon(producer.start)
        values = await consume()
        producer.join(timeout=1)
        assert not producer.is_alive()
        return values

    assert asyncio.run(exercise()) == [1, 2, 3]
    work.join()
    work.close()


def test_closed_queue_rejects_new_work():
    work: AsyncWakeQueue[object] = AsyncWakeQueue()
    work.close()
    try:
        work.put(object())
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("closed queue accepted work")

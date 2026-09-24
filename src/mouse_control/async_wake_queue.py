# SPDX-License-Identifier: AGPL-3.0-or-later
"""Thread-to-asyncio queue without timer polling."""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Generic, TypeVar


T = TypeVar("T")


class AsyncWakeQueue(Generic[T]):
    """Preserve synchronous producer/join semantics for one async consumer."""

    def __init__(self) -> None:
        self._items: queue.Queue[T] = queue.Queue()
        self._state_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiter: asyncio.Future[None] | None = None
        self._closed = False

    def put(self, item: T) -> None:
        with self._state_lock:
            if self._closed:
                raise RuntimeError("async wake queue is closed")
            self._items.put(item)
            loop, waiter = self._loop, self._waiter
        if loop is not None and waiter is not None:
            loop.call_soon_threadsafe(self._wake, waiter)

    @staticmethod
    def _wake(waiter: asyncio.Future[None]) -> None:
        if not waiter.done():
            waiter.set_result(None)

    async def get(self) -> T:
        while True:
            with self._state_lock:
                try:
                    return self._items.get_nowait()
                except queue.Empty:
                    loop = asyncio.get_running_loop()
                    waiter = loop.create_future()
                    self._loop, self._waiter = loop, waiter
            try:
                await waiter
            finally:
                with self._state_lock:
                    if self._waiter is waiter:
                        self._loop = self._waiter = None

    def task_done(self) -> None:
        self._items.task_done()

    def join(self) -> None:
        self._items.join()

    def close(self) -> None:
        with self._state_lock:
            self._closed = True

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protocol-neutral single-reader session for learned raw HID protocols.

Unlike HidSession, this layer knows nothing about HID++, report layouts, feature
indexes, or semantic values.  It owns exactly one hidraw reader, serializes
request/reply exchanges, routes unmatched packets to subscribers, and keeps the
transport open for protocols whose behavior depends on session lifetime.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
import threading
import time
from typing import Protocol

from .hid_session import HidrawIo, RawHidTraceEvent

LOG = logging.getLogger(__name__)


class RawPacketMatcher(Protocol):
    """Structural matcher used to correlate one raw response packet."""

    def matches(self, packet: bytes) -> bool: ...


class LearnedHidSessionError(RuntimeError):
    """The learned HID stream is closed, disconnected, or failed."""


@dataclass
class _RawWaiter:
    matcher: RawPacketMatcher
    event: threading.Event
    packet: bytes | None = None
    error: Exception | None = None


class LearnedHidSession:
    """Own all reads for one learned hidraw interface.

    Only the reader thread calls ``io.read``. Requests are serialized so there
    is at most one pending response matcher. Packets that do not satisfy that
    matcher are delivered in-order to raw subscribers instead of being dropped
    or consumed by a competing reader.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        io_factory=HidrawIo,
        timeout: float = 0.25,
        trace_callback: Callable[[RawHidTraceEvent], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

        self._io = io_factory(self.path)
        self._trace_callback = trace_callback
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._waiter: _RawWaiter | None = None
        self._callbacks: list[Callable[[bytes], None]] = []
        self._callback_failures: dict[Callable[[bytes], None], int] = {}
        self._stop = threading.Event()
        self._io_closed = False
        self._disconnect_error: Exception | None = None
        self._thread = threading.Thread(
            target=self._read_loop,
            name="learned-hid-session",
            daemon=True,
        )
        self._thread.start()

    @property
    def closed(self) -> bool:
        return self._stop.is_set()

    @property
    def disconnect_error(self) -> Exception | None:
        with self._state_lock:
            return self._disconnect_error

    def _record_trace(self, direction: str, data: bytes) -> None:
        callback = self._trace_callback
        if callback is None:
            return
        event = RawHidTraceEvent(
            timestamp_ns=time.monotonic_ns(),
            direction=direction,
            path=str(self.path),
            data=bytes(data),
        )
        try:
            callback(event)
        except Exception:
            LOG.warning("learned raw HID trace callback failed", exc_info=True)

    def subscribe(self, callback: Callable[[bytes], None]) -> Callable[[], None]:
        """Receive every packet not claimed as the current request reply."""

        with self._state_lock:
            if self._stop.is_set():
                raise LearnedHidSessionError("learned HID session is closed")
            self._callbacks.append(callback)

        def unsubscribe() -> None:
            with self._state_lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)
                self._callback_failures.pop(callback, None)

        return unsubscribe

    def _close_io_locked(self) -> None:
        if not self._io_closed:
            self._io_closed = True
            try:
                self._io.close()
            except Exception:
                LOG.debug("learned HID close failed", exc_info=True)

    def _fail_session(self, error: Exception) -> None:
        with self._state_lock:
            if self._disconnect_error is None:
                self._disconnect_error = error
            self._stop.set()
            if self._waiter is not None and self._waiter.error is None:
                self._waiter.error = LearnedHidSessionError(str(error))
                self._waiter.event.set()
            self._close_io_locked()

    def exchange(
        self,
        request: bytes,
        response: RawPacketMatcher,
        *,
        timeout: float | None = None,
    ) -> bytes:
        """Write one request and wait for the structurally matching raw reply."""

        request_bytes = bytes(request)
        wait_timeout = self.timeout if timeout is None else float(timeout)
        if wait_timeout <= 0:
            raise ValueError("timeout must be positive")

        with self._request_lock:
            waiter = _RawWaiter(response, threading.Event())
            with self._state_lock:
                if self._stop.is_set():
                    detail = (
                        f": {self._disconnect_error}"
                        if self._disconnect_error is not None
                        else ""
                    )
                    raise LearnedHidSessionError(
                        f"learned HID session is closed{detail}"
                    )
                if self._waiter is not None:
                    raise LearnedHidSessionError(
                        "internal error: learned HID request waiter already exists"
                    )
                self._waiter = waiter

            try:
                try:
                    self._record_trace("tx", request_bytes)
                    self._io.write(request_bytes)
                except OSError as exc:
                    error = LearnedHidSessionError(
                        f"learned HID write failed: {exc}"
                    )
                    self._fail_session(error)
                    raise error from exc

                if not waiter.event.wait(wait_timeout):
                    raise LearnedHidSessionError(
                        "timed out waiting for a matching learned HID response"
                    )
                if waiter.error is not None:
                    if isinstance(waiter.error, LearnedHidSessionError):
                        raise waiter.error
                    raise LearnedHidSessionError(str(waiter.error)) from waiter.error
                if waiter.packet is None:
                    raise LearnedHidSessionError(
                        "learned HID session closed while waiting for a response"
                    )
                return waiter.packet
            finally:
                with self._state_lock:
                    if self._waiter is waiter:
                        self._waiter = None

    def _dispatch(self, packet: bytes) -> None:
        callbacks: tuple[Callable[[bytes], None], ...] = ()
        with self._state_lock:
            waiter = self._waiter
            if waiter is not None:
                try:
                    matched = bool(waiter.matcher.matches(packet))
                except Exception as exc:
                    waiter.error = LearnedHidSessionError(
                        f"learned response matcher failed: {exc}"
                    )
                    waiter.event.set()
                    return
                if matched:
                    waiter.packet = packet
                    waiter.event.set()
                    return
            callbacks = tuple(self._callbacks)

        for callback in callbacks:
            try:
                callback(packet)
                with self._state_lock:
                    self._callback_failures.pop(callback, None)
            except Exception as exc:
                with self._state_lock:
                    failures = self._callback_failures.get(callback, 0) + 1
                    self._callback_failures[callback] = failures
                if failures & (failures - 1) == 0:
                    LOG.warning(
                        "learned HID subscriber failed (%d consecutive): %s",
                        failures,
                        exc,
                        exc_info=True,
                    )

    def _read_loop(self) -> None:
        failure: Exception | None = None
        try:
            while not self._stop.is_set():
                data = self._io.read(0.25)
                if data == b"":
                    raise OSError("hidraw device disconnected")
                if data is None:
                    continue
                packet = bytes(data)
                self._record_trace("rx", packet)
                self._dispatch(packet)
        except Exception as exc:
            failure = exc
        finally:
            if failure is None:
                failure = LearnedHidSessionError("learned HID session closed")
            self._fail_session(
                LearnedHidSessionError(f"learned HID session disconnected: {failure}")
            )

    def close(self) -> None:
        with self._state_lock:
            already_stopped = self._stop.is_set()
            self._stop.set()
            if self._waiter is not None and self._waiter.error is None:
                self._waiter.error = LearnedHidSessionError(
                    "learned HID session closed"
                )
                self._waiter.event.set()
            self._close_io_locked()
        if not already_stopped and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.0)
        elif threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.0)

    def __enter__(self) -> "LearnedHidSession":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

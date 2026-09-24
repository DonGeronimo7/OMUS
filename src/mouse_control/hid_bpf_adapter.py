# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lifecycle shell for a real HID-BPF loader, with conservative fallback.

The loader is injected so kernel-specific code remains byte instrumentation.
This module is testable without BPF privileges and never owns HID transactions.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from .hid_bpf_observation import HidBpfAdmission, HidBpfObservation


class HidBpfLoader(Protocol):
    def attach(self, binding: tuple[object, ...]) -> bool: ...
    def self_test(self) -> tuple[bool, bool, bool]: ...
    def drain(self) -> tuple[HidBpfObservation, ...]: ...
    def detach(self) -> None: ...


@dataclass(frozen=True)
class HidBpfStatus:
    available: bool
    attached: bool
    blockers: tuple[str, ...]


class HidBpfAdapter:
    def __init__(self, loader: HidBpfLoader | None, *, known_safe_kernel: bool) -> None:
        self._loader = loader
        self._safe = known_safe_kernel
        self._binding: tuple[object, ...] | None = None

    def attach(self, binding: tuple[object, ...]) -> HidBpfStatus:
        if self._loader is None:
            return HidBpfStatus(False, False, ("hid-bpf-loader-unavailable",))
        if self._loader.drain():
            return HidBpfStatus(True, False, ("stale-buffer-not-empty",))
        hook, source, descriptor = self._loader.self_test()
        admission = HidBpfAdmission(hook, source, descriptor, all((hook, source, descriptor)), self._safe)
        if not admission.admitted:
            return HidBpfStatus(True, False, admission.blockers)
        if not self._loader.attach(binding):
            return HidBpfStatus(True, False, ("attachment-failed",))
        self._binding = binding
        return HidBpfStatus(True, True, ())

    def observations(self, *, current_generation: int) -> tuple[HidBpfObservation, ...]:
        if self._loader is None or self._binding is None:
            return ()
        rows = self._loader.drain()
        return tuple(row for row in rows if row.binding_key == self._binding
                     and row.generation == current_generation)

    def detach(self) -> None:
        if self._loader is not None and self._binding is not None:
            self._loader.detach()
        self._binding = None

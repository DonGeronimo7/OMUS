# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact-model native Razer backend with mandatory readback verification."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import hashlib

from .base import HardwareBackend, HardwareError
from .capabilities import (
    BatteryCapabilities, BatteryState, DpiCapabilities, DpiRange, DpiState,
    HardwareCapabilities, ReportRateCapabilities,
)
from ..discovery import MouseDevice
from ..generic_hid import GenericHidDevice, discover_hid_devices
from ..native_razer import (
    HidrawRazerSession, RAZER_VENDOR_ID, RazerProductSpec, RazerProtocolError,
    VERIFIED_RAZER_PRODUCTS, _BATTERY, _CHARGING, _EXTENDED_POLLING, _FIRMWARE,
    _LEGACY_POLLING, _decode_battery, _decode_charging, _decode_dpi,
    _decode_firmware, _decode_polling, _dpi_command, _set_dpi_command,
    _set_polling_command,
)


class NativeRazerBackend(HardwareBackend):
    name = "Native Razer"

    def __init__(
        self,
        *,
        discovery: Callable[[MouseDevice], list[GenericHidDevice]] = discover_hid_devices,
        session_factory: Callable[[str | Path], HidrawRazerSession] = HidrawRazerSession,
    ) -> None:
        self._discovery = discovery
        self._session_factory = session_factory
        self._bound: dict[MouseDevice, tuple[HidrawRazerSession, RazerProductSpec]] = {}
        self._bound_descriptors: dict[MouseDevice, str | None] = {}
        self.discovery_pending = False

    def _spec(self, device: MouseDevice) -> RazerProductSpec | None:
        if device.vendor != RAZER_VENDOR_ID or device.product is None:
            return None
        return VERIFIED_RAZER_PRODUCTS.get(device.product)

    def supports_device(self, device: MouseDevice) -> bool:
        if device in self._bound:
            return True
        spec = self._spec(device)
        if spec is None:
            return False
        self.discovery_pending = True
        opened: list[HidrawRazerSession] = []
        responders: list[HidrawRazerSession] = []
        descriptors: list[str | None] = []
        try:
            for interface in self._discovery(device):
                try:
                    session = self._session_factory(interface.path)
                except OSError:
                    continue
                opened.append(session)
                try:
                    session.query(_FIRMWARE, spec.transaction_id)
                except (OSError, RazerProtocolError):
                    continue
                responders.append(session)
                raw = getattr(interface, "report_descriptor", b"")
                descriptors.append(hashlib.sha256(raw).hexdigest() if raw else None)
            if len(responders) > 1:
                raise HardwareError("Native Razer: multiple protocol responders; refusing ambiguous ownership")
            if not responders:
                return False
            selected = responders[0]
            self._bound[device] = (selected, spec)
            self._bound_descriptors[device] = descriptors[0]
            self.discovery_pending = False
            opened.remove(selected)
            return True
        finally:
            for session in opened:
                session.close()

    def _binding(self, device: MouseDevice) -> tuple[HidrawRazerSession, RazerProductSpec]:
        try:
            if not self.supports_device(device):
                raise HardwareError("Native Razer: exact model/protocol responder unavailable")
            return self._bound[device]
        except HardwareError:
            raise
        except Exception as exc:
            raise HardwareError(f"Native Razer binding failed: {exc}") from exc

    def _query(self, device: MouseDevice, command) -> bytes:
        session, spec = self._binding(device)
        try:
            return session.query(command, spec.transaction_id)
        except (OSError, RazerProtocolError, ValueError) as exc:
            raise HardwareError(f"Native Razer transaction failed: {exc}") from exc

    def discovery_protocol(self, device: MouseDevice, physical):
        """Reuse an exact native owner, without treating storage as volatile.

        The existing Razer writer retains its own policy. Discovery does not
        grant new volatile or persistence authority from a storage selector.
        """
        from ..discovery_models import DiscoveredCapability, DiscoveryEvidence, EvidenceLevel, ProtocolMatch
        from ..proof_state import CapabilityProof, OperationProof, ProofState
        from ..protocol_repertoire import RAZER_DPI

        bound = self._bound.get(device)
        if bound is None or getattr(bound[0], "closed", False) or physical.ambiguous:
            return None
        session, spec = bound
        if (device.bustype, device.vendor, device.product) != (
                physical.bus, physical.vendor_id, physical.product_id) or physical.bus != 3:
            return None
        nodes = [node for node in physical.hidraw_nodes if node.path == Path(session.path)
                 and (node.bus, node.vendor_id, node.product_id)
                 == (physical.bus, physical.vendor_id, physical.product_id)]
        if (len(nodes) != 1 or nodes[0].descriptor_sha256 is None
                or self._bound_descriptors.get(device) != nodes[0].descriptor_sha256):
            return None
        proof = CapabilityProof(
            OperationProof("dpi", ProofState.PROVEN, (RAZER_DPI.vendor_evidence,)),
            read_proven=True, capability_identified=True, semantics_known=True,
            values_bounded=spec.maximum_dpi >= 100 and spec.dpi_step > 0,
            packet_known=True, shared_state_safe=True, confirmation_known=True,
            failure_known=True, routing_unambiguous=True, compatible=True,
            volatile_operation=False, runtime_policy_satisfied=True,
        )
        dpi = DiscoveredCapability(
            "dpi", readable=True, writable=False, minimum=100,
            maximum=spec.maximum_dpi, step=spec.dpi_step,
            evidence=[DiscoveryEvidence(
                EvidenceLevel.VALIDATED, "capability-proof",
                "Exact Razer command known; storage/persistence policy not promoted",
                source="native_razer", details=proof.explain(),
            )],
        )
        return ProtocolMatch(
            "razer-rpc90", "classic-90-byte", nodes[0],
            evidence=[DiscoveryEvidence(
                EvidenceLevel.PROVEN, "razer-single-responder",
                "Existing exact-product native owner reused",
                source="native_razer", details={
                    "transaction_id": spec.transaction_id, "dpi_storage": spec.dpi_storage,
                    "report_bytes": 90, "readback": "xy-dpi",
                },
            )],
            metadata={"capabilities": {"dpi": dpi}, "proof_path": "exact"},
        )

    def get_device_name(self, device: MouseDevice) -> str | None:
        return self._binding(device)[1].model

    def get_capabilities(self, device: MouseDevice) -> HardwareCapabilities:
        _session, spec = self._binding(device)
        rates = ((125, 250, 500, 1000, 2000, 4000, 8000)
                 if spec.high_rate_polling else (125, 500, 1000))
        return HardwareCapabilities(
            dpi=DpiCapabilities(
                readable=True, writable=True,
                ranges=(DpiRange(100, spec.maximum_dpi, spec.dpi_step),),
                independent_axes=True,
            ),
            report_rate=ReportRateCapabilities(readable=True, writable=True, values=rates),
            battery=BatteryCapabilities(
                readable=spec.has_battery, percentage=spec.has_battery,
            ),
        )

    def get_firmware(self, device: MouseDevice) -> str | None:
        return _decode_firmware(self._query(device, _FIRMWARE))

    def supports_dpi(self, device: MouseDevice) -> bool:
        return self.supports_device(device)

    def supports_dpi_monitoring(self, device: MouseDevice) -> bool:
        return self.supports_device(device)

    def get_dpi(self, device: MouseDevice) -> tuple[int, int] | None:
        _session, spec = self._binding(device)
        return _decode_dpi(self._query(device, _dpi_command(spec.dpi_storage)))

    def get_dpi_values(self, device: MouseDevice) -> list[int]:
        _session, spec = self._binding(device)
        return list(range(100, spec.maximum_dpi + 1, spec.dpi_step))

    def set_dpi(self, device: MouseDevice, dpi: int) -> DpiState:
        _session, spec = self._binding(device)
        if dpi < 100 or dpi > spec.maximum_dpi or (dpi - 100) % spec.dpi_step:
            raise HardwareError(f"Native Razer: unsupported DPI {dpi}")
        self._query(device, _set_dpi_command(spec.dpi_storage, dpi, dpi))
        actual = self.get_dpi(device)
        if actual != (dpi, dpi):
            raise HardwareError(f"Native Razer DPI verification failed: requested {dpi}, read {actual}")
        return DpiState(dpi, dpi, confirmed=True)

    def supports_polling_rate(self, device: MouseDevice) -> bool:
        return self.supports_device(device)

    def supports_polling_rate_writes(self, device: MouseDevice) -> bool:
        return self.supports_device(device)

    def get_polling_rates(self, device: MouseDevice) -> list[int]:
        values = self.get_capabilities(device).report_rate.values
        return list(values or ())

    def get_polling_rate(self, device: MouseDevice) -> int | None:
        _session, spec = self._binding(device)
        command = _EXTENDED_POLLING if spec.high_rate_polling else _LEGACY_POLLING
        return _decode_polling(self._query(device, command), extended=spec.high_rate_polling)

    def set_polling_rate(self, device: MouseDevice, hz: int) -> int:
        _session, spec = self._binding(device)
        if hz not in self.get_polling_rates(device):
            raise HardwareError(f"Native Razer: unsupported polling rate {hz}")
        if spec.high_rate_polling:
            self._query(device, _set_polling_command(hz, extended=True, argument=0))
            self._query(device, _set_polling_command(hz, extended=True, argument=1))
        else:
            self._query(device, _set_polling_command(hz, extended=False))
        actual = self.get_polling_rate(device)
        if actual != hz:
            raise HardwareError(
                f"Native Razer polling verification failed: requested {hz}, read {actual}")
        return actual

    def supports_battery(self, device: MouseDevice) -> bool:
        return self._binding(device)[1].has_battery

    def get_battery_state(self, device: MouseDevice) -> BatteryState | None:
        if not self.supports_battery(device):
            return None
        percentage = _decode_battery(self._query(device, _BATTERY))
        charging = _decode_charging(self._query(device, _CHARGING))
        return BatteryState(
            percentage=percentage,
            status="charging" if charging else "discharging" if charging is False else None,
        )

    def close(self) -> None:
        bindings, self._bound = self._bound, {}
        self._bound_descriptors.clear()
        for session, _spec in bindings.values():
            session.close()

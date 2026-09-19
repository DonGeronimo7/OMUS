"""Auditable CLI-to-TUI product capability inventory.

This is a product map, not command dispatch. Machine-only formatting switches
are intentionally excluded; each meaningful operation names its canonical TUI
surface and the shared implementation it uses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductCapability:
    cli: str
    tui_route: str
    shared_implementation: str
    interactive: bool = True
    exclusion_reason: str | None = None


CAPABILITIES = (
    ProductCapability("setup", "Application", "setup_entry.run_tui_setup_wizard"),
    ProductCapability("tui", "Application", "setup_entry.run_tui_setup_wizard"),
    ProductCapability("run", "Service", "cli.run_from_config"),
    ProductCapability("show-config", "Tools / Advanced › Configuration path", "config.get_config_path"),
    ProductCapability("check-permissions", "Tools / Advanced › Permissions", "permissions.permission_report"),
    ProductCapability("debug-dpi", "Discovery Lab › Protocol / evidence", "hidpp_debug.debug_dpi"),
    ProductCapability("debug-hid", "Tools / Advanced › Read-only HID inspection", "generic_hid"),
    ProductCapability("research", "Discovery Lab › Advanced Tools", "hid_corpus"),
    ProductCapability("doctor", "Tools / Advanced › Diagnostics", "doctor"),
    ProductCapability("support", "Tools / Advanced › Support bundle", "support"),
    ProductCapability("discover", "Hardware Discovery", "guided_discovery.run_automatic_discovery"),
    ProductCapability("rediscover", "Hardware Discovery › Retry", "guided_discovery.run_automatic_discovery"),
    ProductCapability("cpi", "Discovery Lab › DPI / CPI investigator", "sensor_calibration"),
    ProductCapability("install-service", "Service", "service.install_service"),
    ProductCapability("start", "Service", "service.start_service"),
    ProductCapability("stop", "Service", "service.stop_service"),
    ProductCapability("restart", "Service", "service.restart_service"),
    ProductCapability("status", "Service", "service.status_service"),
    ProductCapability("update", "Updates", "updater.run_update"),
    ProductCapability("mouse-control-discover", "Hardware Discovery", "discovery_cli"),
    ProductCapability("mouse-control-sensor-calibrate", "Discovery Lab › DPI / CPI investigator", "sensor_calibration"),
    ProductCapability("mouse-control-write-trace", "Discovery Lab › Advanced Tools", "write_trace_cli"),
    ProductCapability("mouse-control-write-promote", "Discovery Lab › Advanced Tools", "write_promotion_cli"),
    ProductCapability("mouse-control-discovery-monitor", "Discovery Lab › Pushed-state / freshness", "discovery_runtime_cli"),
    ProductCapability("mouse-control-polling-promote", "Discovery Lab › Polling investigator", "polling_promotion_cli"),
)


def capability_for_cli(name: str) -> ProductCapability | None:
    return next((item for item in CAPABILITIES if item.cli == name), None)

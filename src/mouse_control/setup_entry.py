"""Production setup transaction around the state-driven full-screen TUI."""

from __future__ import annotations

import logging
import sys

from .setup_flow import restore_dpi
from .setup_tui import run_setup_tui
from .wizard import ButtonCaptureError


def _device_changed(existing_config, selected) -> bool:
    existing_device = existing_config.get("device", {})
    if not isinstance(existing_device, dict):
        existing_device = {}
    configured_phys = existing_device.get("phys")
    return (
        existing_device.get("vendor") != selected.vendor
        or existing_device.get("product") != selected.product
        or (
            bool(configured_phys)
            and bool(selected.phys)
            and configured_phys != selected.phys
        )
    )


def _preference_exists(existing_config, table: str, *keys: str) -> bool:
    value = existing_config.get(table)
    return isinstance(value, dict) and all(key in value for key in keys)


def run_tui_setup_wizard() -> int:
    """Run setup through the TUI while preserving the existing commit/rollback contract."""

    # Import here so this module remains a presentation/transaction adapter and
    # does not create a cli <-> setup_tui import cycle.
    from . import cli

    # The external foreground-session supervisor owns service suspension and
    # restoration.  This process owns only staged configuration and hardware.
    try:
        existing_config = cli._load_setup_config()
    except Exception as exc:
        print(f"Could not load the existing configuration: {exc}", file=sys.stderr)
        return 1
    selected = None
    backend = None
    choices = None
    saved = False
    status = 1

    try:
        mice = cli.get_mouse_devices()
        result = run_setup_tui(
            mice,
            existing_config,
            choices_factory=cli._initial_choices,
            backend_factory=cli.get_backend,
        )
        if not mice:
            status = 0
        else:
            selected = result.selected
            backend = result.backend
            choices = result.choices

            if not result.finished:
                print("Setup cancelled; existing configuration left unchanged.")
                status = 0
            else:
                apply_dpi = (
                    choices.dpi_changed
                    or not _preference_exists(existing_config, "dpi", "active", "stages")
                )
                apply_polling = (
                    choices.polling_changed
                    or not _preference_exists(existing_config, "polling", "rate_hz")
                )

                # Preferences are never write authority. A default/old config may be
                # persisted for software behavior, but hardware application is strictly
                # gated by the capability policy discovered for this exact device.
                dpi_request = choices.active_dpi if (choices.dpi_writable and apply_dpi) else 0
                polling_request = (
                    choices.polling_rate
                    if (choices.polling_writable and apply_polling)
                    else None
                )
                cli._apply_hardware(
                    backend,
                    selected,
                    choices.stages,
                    dpi_request,
                    polling_request,
                    setup=True,
                )
                if choices.lighting_changed:
                    cli._apply_lighting(backend, selected, choices.lighting.values())
                content = cli.merge_setup_config(
                    existing_config,
                    selected,
                    mappings=choices.mappings,
                    dpi_stages=choices.stages,
                    active_dpi=choices.active_dpi,
                    polling_rate_hz=choices.polling_rate,
                    macros=choices.macros,
                    lighting=choices.lighting,
                )
                path = cli.save_config(content)
                saved = True
                print(f"Configuration saved to: {path}")

                if choices.enable_service:
                    try:
                        from .foreground_session import record_service_preference
                        cli.install_service(start=False)
                        record_service_preference(True)
                        print("Mouse Control background service enabled.")
                    except Exception as exc:
                        print(f"Warning: could not enable background service: {exc}")
                        print("Your mouse configuration was still saved successfully.")
                else:
                    try:
                        from .foreground_session import record_service_preference
                        cli.disable_service()
                        record_service_preference(False)
                        print(
                            "Background service disabled. "
                            "You can enable it later with: mouse-control install-service"
                        )
                    except Exception as exc:
                        print(f"Warning: could not disable background service: {exc}")
                        print("Your mouse configuration was still saved successfully.")
                status = 0
    except ButtonCaptureError:
        print("Setup failed; the existing configuration was not changed.", file=sys.stderr)
        status = 1
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled; the existing configuration was not changed.")
        status = 1
    except Exception as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        print("The existing configuration was not changed.", file=sys.stderr)
        status = 1
    finally:
        if not saved and selected is not None and backend is not None and choices is not None:
            try:
                restore_dpi(backend, selected, choices.original_dpi)
            except Exception as exc:
                # Rollback can become impossible after a hardware disconnect;
                # service restoration must still run.
                logging.warning("Could not restore temporary DPI after setup: %s", exc)
    return status

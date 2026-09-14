"""TOML configuration loading and saving."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEFAULT_DPI_STAGES = [800, 1500, 2000, 2500, 3000]
DEFAULT_DPI = 800


def get_config_path() -> Path:
    return Path(os.path.expanduser("~/.config/mouse-control/config.toml"))


def generate_config(
    device_info: Any,
    button_mappings: dict[str, str],
    dpi_stages: list[int] | None = None,
    active_dpi: int = DEFAULT_DPI,
    polling_rate_hz: int | None = None,
) -> str:
    """Generate the human-editable TOML configuration."""
    stages = dpi_stages or DEFAULT_DPI_STAGES
    lines = [
        "# mouse-control configuration",
        "# Actions: passthrough, disable, dpi-cycle, mouse:BTN_*, key:KEY_*, chord:KEY_*+KEY_*",
        "",
        "[device]",
        f'name = {device_info.name!r}',
        f'event_path = {device_info.path!r}',
        f'phys = {getattr(device_info, "phys", "")!r}',
    ]

    if device_info.vendor is not None:
        lines.append(f"vendor = {device_info.vendor}")
    if device_info.product is not None:
        lines.append(f"product = {device_info.product}")

    lines.extend([
        "",
        "[dpi]",
        f"active = {active_dpi}",
        "stages = [" + ", ".join(str(v) for v in stages) + "]",
        "",
        "[polling]",
        f"rate_hz = {polling_rate_hz}" if polling_rate_hz is not None else "# rate_hz = 1000",
        "",
        "[notifications]",
        "dpi_changes = true",
        "",
        "[remap]",
    ])

    for button, action in button_mappings.items():
        lines.append(f'{button!r} = {action!r}')

    return "\n".join(lines) + "\n"


def save_config(config_content: str) -> Path:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(config_content, encoding="utf-8")
    tmp.replace(path)
    return path


def load_config(path: Path | None = None) -> dict[str, Any]:
    import tomllib

    config_path = path or get_config_path()
    with config_path.open("rb") as handle:
        return tomllib.load(handle)

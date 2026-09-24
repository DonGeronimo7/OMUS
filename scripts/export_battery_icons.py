#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Export OMUS tray battery pixmaps for developer visual inspection."""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from mouse_control.battery import battery_pixmap


SIZES = (16, 20, 22, 24, 32)


def _rgba(argb: bytes) -> bytes:
    return b"".join(bytes((red, green, blue, alpha))
                    for alpha, red, green, blue in zip(*[iter(argb)] * 4))


def _png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    rows = b"".join(b"\0" + rgba[row * width * 4:(row + 1) * width * 4]
                    for row in range(height))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _nearest(rgba: bytes, width: int, height: int, scale: int) -> bytes:
    source = [rgba[index:index + 4] for index in range(0, len(rgba), 4)]
    return b"".join(source[y * width + x]
                    for y in range(height) for _ in range(scale)
                    for x in range(width) for _ in range(scale))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--percentage", type=int, default=67)
    parser.add_argument("--output", type=Path, default=Path("battery-icon-previews"))
    parser.add_argument("--scale", type=int, default=8)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        _, _, argb = battery_pixmap(args.percentage, size)
        rgba = _rgba(argb)
        (args.output / f"battery-{args.percentage}-{size}px.png").write_bytes(
            _png(size, size, rgba))
        enlarged = _nearest(rgba, size, size, args.scale)
        enlarged_size = size * args.scale
        (args.output / f"battery-{args.percentage}-{size}px-{args.scale}x.png").write_bytes(
            _png(enlarged_size, enlarged_size, enlarged))


if __name__ == "__main__":
    main()

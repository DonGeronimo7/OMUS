#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replace the generated VirusTotal section in GitHub release notes."""

from __future__ import annotations

import argparse
from pathlib import Path


START = "<!-- virustotal-results:start -->"
END = "<!-- virustotal-results:end -->"


def update(body: str, section: str) -> str:
    if START in body or END in body:
        if body.count(START) != 1 or body.count(END) != 1:
            raise ValueError("malformed existing VirusTotal release-note markers")
        before, remainder = body.split(START, 1)
        _, after = remainder.split(END, 1)
        body = before.rstrip() + after.lstrip("\n")
    return body.rstrip() + "\n\n" + section.strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("body", type=Path)
    parser.add_argument("section", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(
        update(args.body.read_text(encoding="utf-8"), args.section.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Add the deterministic document identity required for CycloneDX attestation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid


PROJECT_ID = "https://github.com/DonGeronimo7/mouse-control"


def finalize(path: Path, version: str) -> str:
    """Validate and finalize a reproducible OMUS CycloneDX document."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("bomFormat") != "CycloneDX" or not document.get("specVersion"):
        raise ValueError("expected a CycloneDX JSON document with a specVersion")

    component = document.get("metadata", {}).get("component", {})
    if component.get("name") != "mouse-control" or component.get("version") != version:
        raise ValueError("SBOM root component does not match the release version")

    serial = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'{PROJECT_ID}@{version}')}"
    document["serialNumber"] = serial
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("version")
    arguments = parser.parse_args()
    print(finalize(arguments.path, arguments.version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

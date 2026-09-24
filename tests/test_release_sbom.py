# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest

from scripts.finalize_cyclonedx_sbom import finalize


def _document(version="0.9.8"):
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": "root-component",
                "name": "omus",
                "type": "application",
                "version": version,
            }
        },
        "components": [],
    }


def test_finalize_adds_stable_cyclonedx_serial_number(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(_document()), encoding="utf-8")
    second.write_text(json.dumps(_document()), encoding="utf-8")

    first_serial = finalize(first, "0.9.8")
    second_serial = finalize(second, "0.9.8")

    assert first_serial == second_serial
    assert first_serial.startswith("urn:uuid:")
    assert first.read_bytes() == second.read_bytes()
    finalized = json.loads(first.read_text(encoding="utf-8"))
    assert finalized["bomFormat"] == "CycloneDX"
    assert finalized["specVersion"] == "1.6"
    assert finalized["serialNumber"] == first_serial
    assert finalized["metadata"]["component"]["licenses"] == [
        {"license": {"id": "AGPL-3.0-or-later"}}
    ]


@pytest.mark.parametrize(
    "document, message",
    [
        ({"bomFormat": "SPDX"}, "CycloneDX"),
        (_document("0.9.7-2"), "release version"),
    ],
)
def test_finalize_rejects_wrong_format_or_release(tmp_path: Path, document, message):
    path = tmp_path / "sbom.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        finalize(path, "0.9.8")

#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fuzz the bounded offline capture importer with all side effects excluded."""

import sys

try:
    import atheris
except ImportError:  # Deterministic harness smoke tests do not need libFuzzer.
    atheris = None


if atheris is not None:
    with atheris.instrument_imports():
        from mouse_control.vendor_capture import (
            VendorCaptureError,
            import_vendor_capture_bytes,
        )
else:
    from mouse_control.vendor_capture import (
        VendorCaptureError,
        import_vendor_capture_bytes,
    )


MAX_INPUT_BYTES = 64 * 1024


def TestOneInput(data: bytes) -> None:
    if len(data) > MAX_INPUT_BYTES:
        return
    try:
        import_vendor_capture_bytes(
            data,
            filename="fuzz-input.json",
            import_date="2000-01-01",
        )
    except VendorCaptureError:
        # Rejected format, schema, provenance, and record data are expected.
        pass


def main() -> None:
    if atheris is None:
        raise SystemExit(
            "Atheris is required; install requirements/fuzz.lock.txt on a "
            "supported Python with --require-hashes --only-binary=:all:."
        )
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()

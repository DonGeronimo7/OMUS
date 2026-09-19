#!/usr/bin/env python3
"""Fuzz bounded HID descriptor and report decoding without opening hardware."""

import sys

try:
    import atheris
except ImportError:  # Deterministic harness smoke tests do not need libFuzzer.
    atheris = None


if atheris is not None:
    with atheris.instrument_imports():
        from mouse_control.hid_descriptor import parse_report_descriptor
        from mouse_control.hid_report import decode_report
else:
    from mouse_control.hid_descriptor import parse_report_descriptor
    from mouse_control.hid_report import decode_report


MAX_INPUT_BYTES = 16 * 1024


def TestOneInput(data: bytes) -> None:
    if len(data) > MAX_INPUT_BYTES:
        return
    if data.startswith(b"hex:"):
        try:
            data = bytes.fromhex(data[4:].decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return
    descriptor = parse_report_descriptor(data)
    for report_type in ("input", "output", "feature"):
        try:
            decode_report(descriptor, data, report_type=report_type)
        except ValueError:
            # Unknown IDs and short/malformed reports are normal fuzz inputs.
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

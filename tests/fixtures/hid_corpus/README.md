# HID semantic corpus

This directory is reserved for sanitized captures from real hardware.  No
device-labelled fixture is committed until it is captured from that physical
device; synthetic descriptors belong in unit tests so they cannot be mistaken
for hardware evidence.

Corpus device directories use `mouse-control-hid-corpus-schema: 1` and contain
raw binary descriptors plus labelled JSONL Input reports.  `device.json` must
exclude serial numbers, node paths, hostnames, usernames, and USB topology.

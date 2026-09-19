from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fuzz.hid_descriptor_fuzzer import TestOneInput as fuzz_hid_descriptor
from fuzz.vendor_capture_fuzzer import TestOneInput as fuzz_vendor_capture


def test_hid_descriptor_fuzz_target_smoke():
    seed = (ROOT / "fuzz/corpus/hid_descriptor_fuzzer/minimal-mouse.hex").read_bytes()
    for data in (b"", b"\xfe", bytes(range(256)), seed):
        fuzz_hid_descriptor(data)


def test_vendor_capture_fuzz_target_smoke():
    seed = (ROOT / "fuzz/corpus/vendor_capture_fuzzer/minimal.json").read_bytes()
    for data in (b"", b"{", b"[]", b'{"schema":null}', seed):
        fuzz_vendor_capture(data)

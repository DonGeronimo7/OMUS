#!/bin/sh
set -eu

# Install requirements/fuzz.lock.txt with --require-hashes and
# --only-binary=:all: in an isolated supported-Python environment first. These
# short runs exercise Atheris startup; ClusterFuzzLite supplies sustained jobs.
python fuzz/hid_descriptor_fuzzer.py -runs=100 fuzz/corpus/hid_descriptor_fuzzer
python fuzz/vendor_capture_fuzzer.py -runs=100 fuzz/corpus/vendor_capture_fuzzer

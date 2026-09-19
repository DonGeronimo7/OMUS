#!/bin/sh
set -eu

# Run from the repository root with pip-tools installed in an isolated
# environment.  Keep one complete lock per workflow environment so every
# transitive dependency is explicit and hash checked by pip.
for name in lock-tools runtime build ci security sbom fuzz; do
    python -m piptools compile \
        --allow-unsafe \
        --generate-hashes \
        --index-url https://pypi.org/simple \
        --no-emit-index-url \
        --strip-extras \
        --output-file "requirements/${name}.lock.txt" \
        "requirements/${name}.in"
    # Host pip configuration can cause pip-tools to echo an irrelevant
    # --no-index flag in the generated comment even when an index was supplied.
    sed -i 's/ --no-index//' "requirements/${name}.lock.txt"
done

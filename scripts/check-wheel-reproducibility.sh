#!/bin/sh
set -eu

first=$(mktemp -d "${TMPDIR:-/tmp}/mouse-control-wheel-a.XXXXXX")
second=$(mktemp -d "${TMPDIR:-/tmp}/mouse-control-wheel-b.XXXXXX")
trap 'rm -rf "$first" "$second"' EXIT HUP INT TERM

git archive --format=tar HEAD | tar -xf - -C "$first"
git archive --format=tar HEAD | tar -xf - -C "$second"

epoch=$(git log -1 --format=%ct HEAD)
for source in "$first" "$second"; do
    (
        cd "$source"
        SOURCE_DATE_EPOCH="$epoch" TZ=UTC LC_ALL=C.UTF-8 \
            python3 -m build --no-isolation --wheel --outdir dist >/dev/null
    )
done

first_wheel=$(find "$first/dist" -maxdepth 1 -type f -name '*.whl' -print -quit)
second_wheel=$(find "$second/dist" -maxdepth 1 -type f -name '*.whl' -print -quit)
test -n "$first_wheel"
test -n "$second_wheel"
test "$(basename "$first_wheel")" = "$(basename "$second_wheel")"
cmp "$first_wheel" "$second_wheel"
sha256sum "$first_wheel"

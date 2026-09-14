#!/bin/sh
set -eu

test "$(uname -m)" = x86_64

PY_RUNTIME_RELEASE="20260901"

version=$(
  python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
)

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

rm -rf AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications

echo "Downloading portable CPython 3.12 runtime..."

curl --fail --location --retry 3 \
  "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/${PY_RUNTIME_RELEASE}" \
  -o "$tmpdir/python-release.json"

python_url=$(
  python3 -c '
import json, re, sys
release = json.load(open(sys.argv[1], encoding="utf-8"))
pattern = re.compile(r"^cpython-3\.12\.\d+\+20260901-x86_64-unknown-linux-gnu-install_only_stripped\.tar\.gz$")
matches = [
    a["browser_download_url"]
    for a in release["assets"]
    if pattern.fullmatch(a["name"])
]
if len(matches) != 1:
    raise SystemExit(f"Expected exactly one CPython 3.12 runtime, found {len(matches)}")
print(matches[0])
' "$tmpdir/python-release.json"
)

curl --fail --location --retry 3 \
  "$python_url" \
  -o "$tmpdir/python-runtime.tar.gz"

tar -xzf "$tmpdir/python-runtime.tar.gz" -C AppDir/usr

bundled_python="$PWD/AppDir/usr/python/bin/python3"

"$bundled_python" -c '
import sys
assert sys.version_info[:2] == (3, 12), sys.version
print("Bundled Python:", sys.version)
'

if ! "$bundled_python" -m pip --version >/dev/null 2>&1; then
  "$bundled_python" -m ensurepip
fi

CC=gcc "$bundled_python" -m pip install \
  --disable-pip-version-check \
  --no-compile \
  .

cat > AppDir/usr/bin/mouse-control <<'EOF'
#!/bin/sh
appdir=${APPDIR:-}
if [ -z "$appdir" ]; then
  appdir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fi

exec "$appdir/usr/python/bin/python3" -m mouse_control.cli "$@"
EOF

chmod +x AppDir/usr/bin/mouse-control

install -Dm644 packaging/appimage/mouse-control.desktop \
  AppDir/usr/share/applications/mouse-control.desktop

for size in 512 256 128 64 48 32; do
  install -Dm644 \
    "assets/icons/hicolor/${size}x${size}/apps/mouse-control.png" \
    "AppDir/usr/share/icons/hicolor/${size}x${size}/apps/mouse-control.png"
done

install -Dm644 packaging/appimage/mouse-control.desktop \
  AppDir/mouse-control.desktop

install -Dm644 assets/icons/hicolor/256x256/apps/mouse-control.png \
  AppDir/mouse-control.png

cat > AppDir/AppRun <<'EOF'
#!/bin/sh
appdir=${APPDIR:-}
if [ -z "$appdir" ]; then
  appdir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
fi

export APPDIR="$appdir"
exec "$appdir/usr/bin/mouse-control" "$@"
EOF

chmod +x AppDir/AppRun

appimagetool AppDir "Mouse-Control-${version}-x86_64.AppImage"

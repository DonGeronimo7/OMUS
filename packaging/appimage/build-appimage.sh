#!/bin/sh
set -eu

test "$(uname -m)" = x86_64

PY_RUNTIME_RELEASE="20260901"
PY_RUNTIME_SHA256="72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c"
PY_RUNTIME_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RUNTIME_RELEASE}/cpython-3.12.14%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"

version=$(
  python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
)

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

rm -rf AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/doc/mouse-control

echo "Downloading pinned portable CPython 3.12 runtime..."

curl --fail --location --retry 3 \
  "$PY_RUNTIME_URL" \
  -o "$tmpdir/python-runtime.tar.gz"

printf '%s  %s\n' "$PY_RUNTIME_SHA256" "$tmpdir/python-runtime.tar.gz" | sha256sum --check --strict -

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

# The AppImage enters Mouse Control through usr/bin/mouse-control below.  Drop
# pip's redundant entry points, whose build-time shebangs refer to the AppDir's
# temporary absolute path, and remove bytecode shipped by the portable runtime.
for script in \
  mouse-control \
  mouse-control-launcher \
  mouse-control-discover \
  mouse-control-discovery-monitor \
  mouse-control-polling-promote \
  mouse-control-sensor-calibrate \
  mouse-control-write-promote \
  mouse-control-write-trace
do
  rm -f "AppDir/usr/python/bin/$script"
done
find AppDir -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find AppDir -type d -name __pycache__ -empty -delete

cat > AppDir/usr/bin/mouse-control <<'EOF'
#!/bin/sh
appdir=${APPDIR:-}
if [ -z "$appdir" ]; then
  appdir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fi

exec "$appdir/usr/python/bin/python3" -m mouse_control "$@"
EOF

chmod +x AppDir/usr/bin/mouse-control

cat > AppDir/usr/bin/mouse-control-launcher <<'EOF'
#!/bin/sh
appdir=${APPDIR:-}
if [ -z "$appdir" ]; then
  appdir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fi

exec "$appdir/usr/python/bin/python3" -m mouse_control.graphical_launcher "$@"
EOF

chmod +x AppDir/usr/bin/mouse-control-launcher

install -Dm644 packaging/appimage/mouse-control.desktop \
  AppDir/usr/share/applications/mouse-control.desktop
install -Dm644 CREDITS.md AppDir/usr/share/doc/mouse-control/CREDITS.md
install -Dm644 SECURITY.md AppDir/usr/share/doc/mouse-control/SECURITY.md

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
if [ "$#" -eq 0 ] && { [ ! -t 0 ] || [ ! -t 1 ]; }; then
  export MOUSE_CONTROL_APPIMAGE=${APPIMAGE:-$0}
  exec "$appdir/usr/bin/mouse-control-launcher"
fi
exec "$appdir/usr/bin/mouse-control" "$@"
EOF

chmod +x AppDir/AppRun

appimagetool AppDir "Mouse-Control-${version}-x86_64.AppImage"

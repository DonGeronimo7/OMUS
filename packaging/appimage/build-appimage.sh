#!/bin/sh
set -eu
# Run in a clean x86_64 build environment with appimagetool installed.
test "$(uname -m)" = x86_64
rm -rf AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications
python3 -m pip install --target AppDir/usr/lib/python3/site-packages .
cat > AppDir/usr/bin/mouse-control <<'EOF'
#!/bin/sh
export PYTHONPATH="${APPDIR}/usr/lib/python3/site-packages${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m mouse_control.cli "$@"
EOF
chmod +x AppDir/usr/bin/mouse-control
cat > AppDir/AppRun <<'EOF'
#!/bin/sh
exec "$(dirname "$0")/usr/bin/mouse-control" "$@"
EOF
chmod +x AppDir/AppRun
appimagetool AppDir Mouse-Control-0.6.9-x86_64.AppImage

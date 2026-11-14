#!/usr/bin/env bash
# Usage: packaging/linux/make_appimage.sh <version> <x64|arm64>
# Wraps the PyInstaller folder dist/K-Whisper into an AppImage and a tar.gz.
set -euo pipefail

VERSION="$1"
ARCH="$2"
case "$ARCH" in
  x64) TOOL_ARCH=x86_64 ;;
  arm64) TOOL_ARCH=aarch64 ;;
  *) echo "unknown arch $ARCH" >&2; exit 1 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
APPDIR="build/AppDir"
NAME="K-Whisper-${VERSION}-linux-${ARCH}"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a dist/K-Whisper "$APPDIR/usr/lib/k-whisper"
cp "$HERE/k-whisper.desktop" "$APPDIR/k-whisper.desktop"
cp "$HERE/k-whisper.desktop" "$APPDIR/usr/share/applications/"
cp src/k_whisper/resources/icon.png "$APPDIR/k-whisper.png"
cp src/k_whisper/resources/icon.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/k-whisper.png"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/k-whisper/K-Whisper" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="build/appimagetool-${TOOL_ARCH}.AppImage"
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${TOOL_ARCH}.AppImage"
  chmod +x "$TOOL"
fi
# CI runners have no FUSE; let the tool extract itself instead of mounting.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$TOOL_ARCH" "$TOOL" --no-appstream "$APPDIR" "dist/${NAME}.AppImage"

tar -C dist -czf "dist/${NAME}.tar.gz" K-Whisper
echo "Created dist/${NAME}.AppImage and dist/${NAME}.tar.gz"

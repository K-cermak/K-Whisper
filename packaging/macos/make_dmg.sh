#!/usr/bin/env bash
# Usage: packaging/macos/make_dmg.sh <version>   (run after PyInstaller; writes dist/K-Whisper-<version>-macos-arm64.dmg)
set -euo pipefail

VERSION="$1"
APP="dist/K-Whisper.app"
OUT="dist/K-Whisper-${VERSION}-macos-arm64.dmg"
STAGING="$(mktemp -d)"

# Without an Apple Developer ID the app gets an ad-hoc signature; users confirm it once in
# System Settings > Privacy & Security (or right-click > Open).
codesign --force --deep --sign - "$APP"

cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "K-Whisper" -srcfolder "$STAGING" -ov -format UDZO "$OUT"
rm -rf "$STAGING"
echo "Created $OUT"

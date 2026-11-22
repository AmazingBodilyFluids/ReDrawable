#!/bin/bash
# Builds ReDrawable.app and ReDrawable-<version>-mac-<arch>.dmg in mac/dist/, for the CPU of the
# Mac it runs on (arm64 = Apple silicon, x86_64 = Intel). The app carries its own Python, so the
# user's Mac needs no Python, pip or Homebrew.
#
# 1. Downloads a relocatable CPython (astral-sh/python-build-standalone, "install_only") and
#    pip-installs pc/requirements.txt into it (pywebview pulls in pyobjc on a Mac).
# 2. Compiles mac/launcher.c as Contents/MacOS/ReDrawable, which runs pc/app.py on that Python
#    in its own process, so the Dock, the menu bar and the Accessibility list say "ReDrawable".
# 3. Copies the app with the repo's layout (pc/, tablet/) into Contents/Resources/app.
# 4. Signs everything ad hoc (no Apple Developer ID: Gatekeeper will ask the user to allow it
#    once, see mac/README-mac.md) and packs the .app into a .dmg with a link to Applications.
#
# Usage: mac/build_app.sh            (PY_MINOR=3.13 by default)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
BUILD="$HERE/build"
DIST="$HERE/dist"
PY_MINOR="${PY_MINOR:-3.13}"
ARCH="$(uname -m)"
case "$ARCH" in arm64) TRIPLE=aarch64-apple-darwin ;; x86_64) TRIPLE=x86_64-apple-darwin ;;
  *) echo "unknown CPU $ARCH"; exit 1 ;; esac
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/pc/version.py")"
echo "ReDrawable $VERSION for $ARCH"

rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD" "$DIST"
APP="$BUILD/ReDrawable.app"
C="$APP/Contents"
mkdir -p "$C/MacOS" "$C/Resources/app/pc" "$C/Resources/app/tablet/companion"

# ---- 1. Python
if [ -z "${PY_URL:-}" ]; then
  AUTH=()
  [ -n "${GH_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GH_TOKEN")
  PY_URL="$(curl -fsSL "${AUTH[@]}" https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest |
    python3 -c "
import json, re, sys
pat = re.compile(r'cpython-${PY_MINOR//./\\.}\.\d+\+\d+-${TRIPLE}-install_only\.tar\.gz$')
print(next(a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if pat.search(a['name'])))")"
fi
echo "Python: $PY_URL"
curl -fsSL "$PY_URL" -o "$BUILD/python.tar.gz"
tar -xzf "$BUILD/python.tar.gz" -C "$C/Resources"   # -> Resources/python
PY="$C/Resources/python/bin/python3"
PYLIB="$(cd "$C/Resources/python/lib" && ls libpython${PY_MINOR}*.dylib | head -1)"
echo "libpython: $PYLIB"
"$PY" -m pip install --disable-pip-version-check --no-warn-script-location -r "$REPO/pc/requirements.txt"
# not needed at run time
rm -rf "$C/Resources/python/lib/python${PY_MINOR}/test" "$C/Resources/python/lib/python${PY_MINOR}/idlelib" \
       "$C/Resources/python/lib/python${PY_MINOR}/tkinter" "$C/Resources/python/lib/python${PY_MINOR}/turtledemo" \
       "$C/Resources/python/share" "$C/Resources/python/include"

# ---- 2. launcher
clang -O2 -Wall -mmacosx-version-min=11.0 -DPY_LIB="\"$PYLIB\"" -o "$C/MacOS/ReDrawable" "$HERE/launcher.c"

# ---- 3. the app, laid out as in the repo (app.py finds web/, icons/ and ../tablet/ next to itself)
find "$REPO/pc" -maxdepth 1 -name '*.py' ! -name 'test_*' -exec cp {} "$C/Resources/app/pc/" \;
cp "$REPO/pc/requirements.txt" "$C/Resources/app/pc/"
cp -R "$REPO/pc/web" "$REPO/pc/icons" "$C/Resources/app/pc/"
for f in tablet/rmpp-pen tablet/rmpp-pen-armv7 tablet/companion/rmpp-companion tablet/companion/rmpp-companion-rm2 \
         tablet/companion/rmpp-companion-rm1 tablet/companion/run.sh; do
  cp "$REPO/$f" "$C/Resources/app/$f"
done
cp "$REPO"/tablet/*.pdf "$C/Resources/app/tablet/"
cp "$REPO/LICENSE" "$C/Resources/app/"
# "installed" (pc/paths.py): logs go to ~/Library/Application Support/ReDrawable, never into the .app
echo "Installed copy: settings and log in ~/Library/Application Support/ReDrawable" > "$C/Resources/app/installed"
"$PY" -m compileall -q "$C/Resources/app/pc" "$C/Resources/python/lib/python${PY_MINOR}" || true

# icon: the 256 px PNG, through Pillow's ICNS writer (a throwaway venv on the build Mac's Python)
python3 -m venv "$BUILD/iconenv"
"$BUILD/iconenv/bin/pip" -q install pillow
"$BUILD/iconenv/bin/python" -c "
from PIL import Image
Image.open('$REPO/pc/icons/redrawable.png').convert('RGBA').save('$C/Resources/ReDrawable.icns',
    sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256)])"

sed -e "s/@VERSION@/$VERSION/g" "$HERE/Info.plist" > "$C/Info.plist"
plutil -lint "$C/Info.plist"

# ---- 4. sign ad hoc (inner code first), then the .dmg
find "$C/Resources" -type f \( -name '*.so' -o -name '*.dylib' \) -exec codesign --force --sign - {} \;
codesign --force --sign - "$C/Resources/python/bin/python${PY_MINOR}"
codesign --force --sign - "$APP"  # no hardened runtime: it only matters for notarization
codesign --verify --verbose=2 "$APP"

DMG="$DIST/ReDrawable-$VERSION-mac-$ARCH.dmg"
STAGE="$BUILD/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "ReDrawable $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG"
cp -R "$APP" "$DIST/"
(cd "$DIST" && shasum -a 256 "$(basename "$DMG")")
echo "Built $DMG"

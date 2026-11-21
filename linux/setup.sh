#!/bin/sh
# One-time setup of ReDrawable on Linux. Safe to run again.
#  1. system packages for the window (GTK WebKit): Arch / Omarchy (pacman) and Fedora (dnf); others: printed
#  2. a private Python environment with paramiko and pywebview
#  3. access to /dev/uinput (udev rule + load the module at boot)   [sudo]
#  4. a menu entry
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="$DATA/redrawable/venv"

echo "== 1/4 System packages"
if command -v pacman >/dev/null 2>&1; then
  # libinput (with its debug-events tool) is part of every Arch desktop already
  sudo pacman -S --needed python python-gobject webkit2gtk-4.1
elif command -v dnf >/dev/null 2>&1; then
  # libinput-utils: the `libinput` command linux/check_devices.py uses
  sudo dnf install -y python3 python3-gobject webkit2gtk4.1 libinput-utils
else
  echo "Not Arch or Fedora: install Python 3.10+, PyGObject and WebKitGTK yourself, e.g."
  echo "  Debian/Ubuntu: sudo apt install python3-venv python3-gi gir1.2-webkit2-4.1 libinput-tools"
fi

echo "== 2/4 Python environment in $VENV"
python3 -m venv --system-site-packages "$VENV"   # system site: PyGObject comes from the OS
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$DIR/pc/requirements.txt"

echo "== 3/4 Permission to create the virtual pen (/dev/uinput)"
sudo install -m 644 "$DIR/linux/60-redrawable-uinput.rules" /etc/udev/rules.d/60-redrawable-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/redrawable-uinput.conf >/dev/null
# the same rule and module file from the Paper Tablet test builds
sudo rm -f /etc/udev/rules.d/60-paper-tablet-uinput.rules /etc/modules-load.d/paper-tablet-uinput.conf
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput || true

echo "== 4/4 Menu entry"
mkdir -p "$DATA/applications"
chmod +x "$DIR/linux/redrawable.sh"
rm -f "$DATA/applications/paper-tablet.desktop"
cat > "$DATA/applications/redrawable.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ReDrawable
Comment=reMarkable tablet as a pen tablet
Exec=$DIR/linux/redrawable.sh
Icon=$DIR/pc/icons/redrawable.png
Terminal=false
Categories=Graphics;Utility;
StartupWMClass=redrawable
DESKTOP

echo
if [ -w /dev/uinput ]; then
  echo "Done. Start ReDrawable from your app launcher, or run: $DIR/linux/redrawable.sh"
else
  echo "Done. Log out and back in once (so the new /dev/uinput permission applies),"
  echo "then start ReDrawable from your app launcher, or run: $DIR/linux/redrawable.sh"
fi

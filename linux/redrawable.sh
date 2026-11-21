#!/bin/sh
# Start ReDrawable from this folder (made by linux/setup.sh).
DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/redrawable/venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "ReDrawable isn't set up yet: run $DIR/linux/setup.sh first." >&2
  exit 1
fi
exec "$VENV/bin/python" "$DIR/pc/app.py" "$@"

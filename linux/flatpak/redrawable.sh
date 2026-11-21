#!/bin/sh
# Flatpak launcher. Settings live in ~/.config/ReDrawable like a from-source install (see the manifest).
exec python3 /app/share/redrawable/pc/app.py "$@"

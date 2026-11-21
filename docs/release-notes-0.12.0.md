ReDrawable 0.12.0 turns a reMarkable Paper Pro into a pressure-sensitive pen tablet for **Windows** and now also **Linux** (beta).

## Downloads

**Windows**
- **`ReDrawable-Setup-0.12.0.exe`** installs for your user account. No admin rights are needed.
- **`ReDrawable-Portable-0.12.0.zip`**: unzip it anywhere and run it. Settings stay in its `data` folder.

Neither needs Python. Upgrading from 0.11.0 keeps your settings.

**Linux (beta)**
- **`ReDrawable-0.12.0-x86_64.AppImage`**: `chmod +x` it and run it. On Arch / Omarchy you may need `fuse2` first.
- **`ReDrawable-0.12.0.flatpak`**: `flatpak install --user ./ReDrawable-0.12.0.flatpak`. It needs the GNOME 48 runtime from Flathub.

On first start, go to *Settings → Pen device → Allow*. It asks for your password once, so that the app can create its virtual pen.

## New

- **Linux version.** It works on Wayland (Hyprland, GNOME, KDE, Sway) and on X11:
  - a virtual pen tablet with pressure, tilt, hover and the eraser
  - shortcuts, pan and rotate
  - an optional virtual touchscreen
  - a tray icon
  - Krita's keys as the default panel
  Linux was tested on Omarchy.
- **Three tablet panels: Shortcuts, Mask and Tracing image.** Each panel has its own corner tab, and they all open in the same place. Opening one folds the others.
- **Button setting** for each panel:
  - *Default* works as before.
  - *Pen hover* hides a folded panel's tab until the pen hovers along that edge, so you can draw into the corner. A pen tap on the tab opens the panel.
  - *Finger only* keeps the panel shown. The pen draws straight through it, and only fingers press its buttons.
- **Panel & gestures page:**
  - Shortcuts, Gestures, Mask and Tracing each have their own page, in that order.
  - *Edit Left / Right* unfolds that panel and shows it close up. Scroll to see the rest of it.
- **Recording keys:** the first key you press ends the recording. Esc or a click elsewhere cancels it. The rotate key is recorded the same way.
- **Touchscreen / Windows touch** finger modes now turn the tablet's own finger gestures off. *Shortcuts* turns them back on.
- **The Tracing image panel** holds several images. You pick one on the tablet, and each image keeps its own place and strength.

## Fixed

- The five-finger rotate drag now fits small screens. On a 768 px screen it used to start in the app's toolbar.
- The app no longer crashes when masks change while the tablet's mask strip is being drawn.
- Naming a new mask with a name that was already taken no longer hangs the app.
- The tablet's "fallen behind" warning is now logged once a minute, so it no longer floods the log.

## Notes

- Tested on a reMarkable Paper Pro with firmware 3.29. reMarkable 2 and 1 support is still beta and has not been tried on real hardware.
- The Windows builds aren't code-signed yet. SmartScreen may warn the first time: click *More info*, then *Run anyway*.
- `SHA256SUMS.txt` lists the checksum of every download.

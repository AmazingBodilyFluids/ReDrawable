# ReDrawable on Linux (beta)

Status: **beta, not yet tested with a tablet on a real Linux desktop.** The same app as the Windows
release (0.11.0), with a Linux back end. It is written for Wayland desktops that use libinput (Hyprland,
GNOME, KDE, Sway) and for X11. Targets for the first test: **Omarchy** (Arch + Hyprland) and **Fedora**
(GNOME).

## Install

```sh
git clone -b claude/project-thread-1exdyu https://github.com/AmazingBodilyFluids/ReDrawable.git redrawable
cd redrawable
./linux/setup.sh
```

`setup.sh` does four things, and asks for `sudo` where needed:
1. Installs the window libraries: on Arch `python-gobject` and `webkit2gtk-4.1` (pacman), on Fedora
   `python3-gobject`, `webkit2gtk4.1` and `libinput-utils` (dnf). Elsewhere it prints what to install.
2. Creates a private Python environment in `~/.local/share/redrawable/venv` with paramiko and pywebview.
3. Adds a udev rule so your user may create virtual input devices (`/dev/uinput`, the same rule Steam
   uses for controllers), and loads the `uinput` module at boot.
4. Adds a "ReDrawable" entry to your app launcher.

Log out and back in once afterwards. Then start ReDrawable from the launcher, or run
`linux/redrawable.sh`. The setup guide in the app does the rest.

## How it works on Linux

- **Pen.** The app creates a virtual pen tablet ("ReDrawable Pen") through uinput. Your desktop sees it
  like a USB tablet, with hover, pressure, tilt and the eraser end. Krita, GIMP, Inkscape, Xournal++ and
  other apps get it through their normal tablet support.
- **Shortcuts, pan and rotate** go through a virtual keyboard and an absolute mouse ("ReDrawable Keys" /
  "ReDrawable Mouse"). The default panel and the built-in preset are **Krita**'s default keys.
- **Monitors** come from `hyprctl` on Hyprland, and from GTK elsewhere (GNOME, KDE), with `xrandr` as a
  last resort.
- **The focused app** (for hold-to-snap's allow-list and the rotate gesture's centre) is only known on
  Hyprland. GNOME and KDE don't tell other programs which window is in front, so there hold-to-snap works
  in every app while its switch is on, and rotate turns round the middle of the screen.
- **Touchscreen mode.** The *Touchscreen* finger mode creates a virtual touchscreen ("ReDrawable Touch"),
  so apps scroll with inertia and pinch-zoom by themselves.
- **Splash and tray.** The splash shows on GNOME, KDE and X11 as a small window. It is skipped on tiling
  compositors (Hyprland, Sway, i3), which would tile it. `REDRAWABLE_SPLASH=1` or `=0` forces it. There is
  no tray icon: closing the window quits the app.

## Things to check if something's off

- **Check the virtual devices without the tablet.** `python3 linux/check_devices.py` creates the pen, touch,
  keyboard and mouse, sends a short hover, and prints what libinput sees (needs the `libinput` command: part
  of Arch's `libinput`, Fedora's `libinput-utils`; run it with `sudo` if the event list stays empty).
  `--full` also draws, erases, touches and drags: use it over an empty desktop.
- **"No access to /dev/uinput".** Run `setup.sh` again, log out and in, then check `ls -l /dev/uinput`.
  It should show a `+` (an ACL for your user).
- **The tablet isn't found.** The tablet's USB network must give your PC an address in `10.11.99.x`. Check
  `ip -4 addr | grep 10.11.99`. NetworkManager (Fedora, and Omarchy) does this by itself. With plain
  systemd-networkd, add `/etc/systemd/network/50-remarkable.network` containing

  ```ini
  [Match]
  Driver=rndis_host cdc_ether cdc_ncm

  [Network]
  DHCP=ipv4
  ```

  then run `sudo systemctl restart systemd-networkd`.
- **The pen lands in the wrong place.** The app maps the tablet across all monitors itself. On Hyprland,
  leave `input:tablet:output` and `region_*` unset. On GNOME, leave *Settings → Wacom Tablet* alone for
  "ReDrawable Pen" (map to all screens). Choose the display on the app's *Calibrate* page instead.
- **Krita doesn't react to the pen (Wayland).** Krita's native Wayland mode can ignore a virtual tablet.
  Start it through XWayland instead: `QT_QPA_PLATFORM=xcb krita`.
- **The rotate gesture** needs the app's own rotate-view key, set on *Panel & gestures → Gestures*:
  `shift+space` for Krita, `r` for apps that use R.

Settings are in `~/.config/ReDrawable/` (carried over once from `~/.config/PaperTablet/` if you ran a
Paper Tablet test build). Started from the launcher, the app logs to `pc/redrawable.log` in this folder;
started with `linux/redrawable.sh` in a terminal, it prints there instead.

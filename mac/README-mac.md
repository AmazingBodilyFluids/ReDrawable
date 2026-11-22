# ReDrawable on a Mac (beta)

The Mac app turns the reMarkable into a pen tablet for macOS with hover, pressure, tilt and the
eraser end, the tablet screen and its panels, finger gestures as shortcuts, Wi-Fi and calibration:
the same app as on Windows and Linux.

## Install

1. Download `ReDrawable-<version>-mac-arm64.dmg` (Apple silicon: M1 and later) or
   `...-mac-x86_64.dmg` (Intel Macs), open it and drag ReDrawable to Applications.
2. The app is not signed with an Apple Developer ID, so the first start is blocked. Open
   **System Settings → Privacy & Security**, scroll down to the message about ReDrawable and press
   **Open Anyway**. (Terminal alternative: `xattr -dr com.apple.quarantine /Applications/ReDrawable.app`.)
3. Plug the tablet in and follow the setup guide in the app.
4. The first time the pen turns on, macOS asks to let ReDrawable control the computer. Allow it in
   **System Settings → Privacy & Security → Accessibility**, then quit and reopen ReDrawable. The
   app's **Settings → Pen permission** row shows whether it is allowed.

After installing a newer build, macOS may treat it as a new app: if the pen stops, remove
ReDrawable from the Accessibility list with the minus button and allow it again. (Ad-hoc signed
apps are identified by their exact build.)

## How it works

The pen is sent as the same events a tablet driver produces: a proximity event (pen or eraser),
then mouse events of the "tablet point" kind carrying pressure and tilt. Photoshop, Krita, Clip
Studio, Affinity and other drawing apps read them like a Wacom pen. Details in `pc/macinput.py`.

- **Keys**: the shortcut names are shared with Windows. Ctrl is sent as **Command** and Alt as
  **Option**, as Photoshop and Krita use them on a Mac; the Win key is **Control**. When recording a
  key in the app, Command is stored as Ctrl, so profiles move between computers unchanged.
- **Touch**: macOS has no way for an app to create touches, so the "Windows touch" profile mode is
  not offered; finger gestures always send shortcuts.
- **Tray**: there is no menu-bar icon yet. Closing the window quits the app.

## USB connection

The tablet's USB network should show up in **System Settings → Network** (reMarkable's own USB web
interface works on Macs over the same link). If the tablet isn't found, unplug it, wait five
seconds and plug it in again, and check that the tablet is awake. Wi-Fi mode (Settings) works too
once set up over the cable.

## Build it yourself

On a Mac with the Xcode command line tools: `mac/build_app.sh`. It downloads its own Python, so it
needs no Homebrew. The result is `mac/dist/ReDrawable.app` and the `.dmg`. The GitHub workflow
`.github/workflows/mac-packages.yml` builds both CPU types and runs `mac/check_events.py`, which
sends a pen stroke, an eraser stroke and keys into a test window and checks what arrived.

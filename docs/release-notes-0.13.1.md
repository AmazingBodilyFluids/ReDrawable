ReDrawable 0.13.1 is a small update to 0.13.0 for **Windows** and **Linux** (beta).

## Downloads

**Windows**
- **`ReDrawable-Setup-0.13.1.exe`** installs for your user account. No admin rights are needed.
- **`ReDrawable-Portable-0.13.1.zip`**: unzip it anywhere and run it. Settings stay in its `data` folder.

Neither needs Python. Upgrading from 0.13.0 keeps your settings.

**Linux (beta)**
- **`ReDrawable-0.13.1-x86_64.AppImage`**: `chmod +x` it and run it. On Arch / Omarchy you may need `fuse2` first.
- **`ReDrawable-0.13.1.flatpak`**: `flatpak install --user ./ReDrawable-0.13.1.flatpak`. It needs the GNOME 48 runtime from Flathub.

On first start, go to *Settings → Pen device → Allow*. It asks for your password once, so that the app can create its virtual pen.

## Changed

- **reMarkable 2 and 1: no light controls.** These tablets have no front light, so the tablet panels no longer show a *Light* button. Its slot stays empty, and the desktop previews match.
  - In *Panel & gestures*, such a button is marked "no light", and the *Light* button type and preset are hidden.
  - The light bar and the *Front light* slider were already hidden on these tablets.
  - The Paper Pro and the Paper Pro Move are unchanged.

## Notes

- Paper Pro Move support (new in 0.13.0) is in beta testing and hasn't yet been run on a real Move.
- Tested on a reMarkable Paper Pro with firmware 3.29. reMarkable 2 and 1 support is still beta and has not been tried on real hardware.
- The Windows builds aren't code-signed yet. SmartScreen may warn the first time: click *More info*, then *Run anyway*.
- `SHA256SUMS.txt` lists the checksum of every download.

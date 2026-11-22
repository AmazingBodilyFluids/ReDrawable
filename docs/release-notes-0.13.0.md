ReDrawable 0.13.0 adds the **reMarkable Paper Pro Move** (beta) to the tablets it turns into a pressure-sensitive pen tablet for **Windows** and **Linux** (beta).

## Downloads

**Windows**
- **`ReDrawable-Setup-0.13.0.exe`** installs for your user account. No admin rights are needed.
- **`ReDrawable-Portable-0.13.0.zip`**: unzip it anywhere and run it. Settings stay in its `data` folder.

Neither needs Python. Upgrading from 0.12.0 keeps your settings.

**Linux (beta)**
- **`ReDrawable-0.13.0-x86_64.AppImage`**: `chmod +x` it and run it. On Arch / Omarchy you may need `fuse2` first.
- **`ReDrawable-0.13.0.flatpak`**: `flatpak install --user ./ReDrawable-0.13.0.flatpak`. It needs the GNOME 48 runtime from Flathub.

On first start, go to *Settings → Pen device → Allow*. It asks for your password once, so that the app can create its virtual pen.

## New

- **Paper Pro Move support (beta).** The app recognises the Move and maps the pen to its 7.3" 16:9 screen.
  - The setup guide lists the Move and takes it through the same developer-mode steps as the Paper Pro.
  - The tablet's panels are half as wide on the Move's smaller screen. Each holds one column of your shortcut buttons, and you drag with a finger to scroll through them. A tap presses a button, and a hold presses a hold button.
  - The Mask and Tracing image lists scroll the same way.
  - The side without the light bar uses the full height for buttons.
  - The finger-gestures button is a touch-point icon.
  - The previews on *Home* and *Panel & gestures* show the Move's screen at its real shape, and the mouse wheel scrolls their panels.
- **Each tablet model keeps its own calibration**, so switching between tablets doesn't undo another tablet's calibration.

## Notes

- The Paper Pro, reMarkable 2 and reMarkable 1 work as in 0.12.0. Their tablet screens and previews are unchanged.
- Paper Pro Move support is in beta testing. It was checked against reMarkable's official Move SDK but hasn't yet been run on a real Move.
- Tested on a reMarkable Paper Pro with firmware 3.29. reMarkable 2 and 1 support is still beta and has not been tried on real hardware.
- The Windows builds aren't code-signed yet. SmartScreen may warn the first time: click *More info*, then *Run anyway*.
- `SHA256SUMS.txt` lists the checksum of every download.

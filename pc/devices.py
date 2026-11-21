"""The reMarkable models the app knows, and how to tell which one is plugged in.

Everything else in the app works in panel terms: the pen helper's raw digitizer axes are turned
to run with the panel's pixels in portrait (X to the right, Y down) as they are read, so
calibration, the tablet screen, shapes and the mask don't need to know the model.

Sources: screen sizes and densities from reMarkable's product specifications; the input
devices and their orientation from reMarkable's own Qt guide (developer.remarkable.com,
touch rotation on rM1 / rM2) and libremarkable (MIT; rM1 / rM2 Wacom digitizer turned 270
degrees against the panel); the Paper Pro from measurements on a real tablet (2026-10-27).

Paper Pro Move ("chiappa", beta, never run on one): codename from developer.remarkable.com
(SDK page, product code names); 1696 x 954 at 264 ppi from remarkable.com's specifications;
"reMarkable Chiappa" in /sys/devices/soc0/machine and a portrait-native pen (X 0-6760,
Y 0-11960) as measured on a Move by goMarkableStream (beyondsimulations fork, MIT). The panel's
size in mm is worked out from the pixels and ppi, not measured.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    screen: tuple          # panel pixels, portrait (width, height)
    panel_mm: tuple        # active area, portrait (width, height)
    helper: str            # pen helper binary in tablet/
    companion: str         # tablet-screen app in tablet/companion/
    pen_rot: int = 0       # quarter turns of the digitizer against the panel, in degrees (0 or 270)
    invert_tilt_y: bool = False  # the digitizer's TILT_Y runs against its Y axis
    frontlight: bool = False
    developer_mode: bool = False  # SSH needs developer mode (which resets the tablet)
    verified: bool = False  # tested on real hardware

    @property
    def px_per_mm(self):
        return self.screen[1] / self.panel_mm[1]

    @property
    def aspect(self):
        """Panel width / height in portrait (0.75 on the Paper Pro, 0.5625 on the Move)."""
        return self.screen[0] / self.screen[1]


MODELS = {
    "ferrari": Model("ferrari", "reMarkable Paper Pro", (1620, 2160), (179.8, 239.8),
                     "rmpp-pen", "rmpp-companion", invert_tilt_y=True, frontlight=True,
                     developer_mode=True, verified=True),
    # 7.3", 954 x 1696 at 264 ppi (16:9). 64-bit like the Paper Pro, so the same pen helper; the
    # Paper Pro's tablet-screen build too: every library and symbol it needs is in reMarkable's
    # chiappa SDK sysroot (3.29.1.0, same Qt 6.10.3 and EPScreenModeItem). Tilt quirk assumed
    # to be the Paper Pro's (same Elan controller family), not measured.
    "chiappa": Model("chiappa", "reMarkable Paper Pro Move", (954, 1696), (91.8, 163.2),
                     "rmpp-pen", "rmpp-companion", invert_tilt_y=True, frontlight=True,
                     developer_mode=True),
    # 10.3", 1404 x 1872 at 226 ppi
    "rm2": Model("rm2", "reMarkable 2", (1404, 1872), (157.8, 210.4),
                 "rmpp-pen-armv7", "rmpp-companion-rm2", pen_rot=270),
    "rm1": Model("rm1", "reMarkable 1", (1404, 1872), (157.8, 210.4),
                 "rmpp-pen-armv7", "rmpp-companion-rm1", pen_rot=270),
}
DEFAULT = MODELS["ferrari"]


def helper_for_arch(machine):
    """The pen helper that runs on a CPU (`uname -m`)."""
    return "rmpp-pen" if machine.startswith("aarch64") else "rmpp-pen-armv7"


def detect(info):
    """The model from the pen helper's `info` (its "model" line is /sys/devices/soc0/machine or
    the device-tree model; older helpers didn't report one)."""
    text = " ".join(str(info.get(k) or "") for k in ("model", "dt_model", "hwrevision")).lower()
    if "chiappa" in text:
        return MODELS["chiappa"]
    if "ferrari" in text:
        return MODELS["ferrari"]
    if "remarkable 2" in text or "remarkable2" in text:
        return MODELS["rm2"]
    if "remarkable 1" in text or "remarkable1" in text or "prototype 1" in text:
        return MODELS["rm1"]
    names = " ".join(d.get("name", "") for d in info.get("devices", [])).lower()
    if not str(info.get("machine", "")).startswith("aarch64") and "wacom" in names:
        # a 32-bit reMarkable that didn't say which: the rM2's touch panel is "pt_mt"
        return MODELS["rm2"] if "pt_mt" in names else MODELS["rm1"]
    return DEFAULT

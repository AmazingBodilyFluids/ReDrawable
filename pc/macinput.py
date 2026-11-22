"""macOS output: the pen, keys and drags as Quartz events (pyobjc's Quartz, which pywebview's
Cocoa backend already installs).

The pen is sent the way a tablet driver sends it to the window server: a proximity event when
the pen comes into range (saying pen or eraser), then mouse events (moved / down / dragged / up)
whose subtype is "tablet point" and which carry pressure and tilt, then a proximity event when it
leaves. Apps read that through NSEvent (pressure, tilt, pointingDeviceType), which is what
Photoshop, Krita (Qt) and the other drawing apps use on a Mac.

Facts this relies on, and where they come from:
- NSEvent.tilt runs -1..1 on both axes, x positive to the right, y positive towards the bottom
  (Apple, NSEvent.tilt), so the same directions as the Windows / Linux frames.
- Qt turns that into degrees as tilt * 60 (qtbase, cocoa/qnsview_tablet.mm), so +-1 is sent for
  +-60 degrees. Qt also drops tablet events from a device id it has not seen a proximity event
  for, so every stroke starts with one.
- Posting events needs the Accessibility permission (CGPreflightPostEventAccess /
  CGRequestPostEventAccess, macOS 10.15 and later).

Frames arrive in "pixels": monitors() hands the rest of the app each display in pixels (points
times its backing scale, so a Retina screen keeps half-point precision), and everything here turns
them back into the global points Quartz wants.
"""
import ctypes
import ctypes.util
import threading

try:
    import Quartz as Q
except ImportError:  # not on a Mac, or pyobjc missing: available() says so
    Q = None

LAST_PEN = None

# Virtual key codes (HIToolbox Events.h, kVK_ANSI_* and kVK_*). Positions on a US layout, which is
# what the Windows virtual keys mean too.
KEYCODE = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08,
    "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19, "7": 0x1A,
    "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "enter": 0x24, "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "tab": 0x30, "space": 0x31, "`": 0x32,
    "backspace": 0x33, "esc": 0x35,
    "ctrl": 0x37,   # Command: Ctrl on Windows is Command on a Mac (Photoshop, Krita, most apps)
    "shift": 0x38,
    "alt": 0x3A,    # Option
    "win": 0x3B,    # Control: the remaining modifier
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F, "f13": 0x69, "f14": 0x6B, "f15": 0x71,
    "f16": 0x6A, "f17": 0x40, "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "insert": 0x72,  # Help, where Insert sits on a full-size Apple keyboard
    "home": 0x73, "pageup": 0x74, "delete": 0x75, "end": 0x77, "pagedown": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}
FLAG = {"ctrl": 0x100000, "shift": 0x20000, "alt": 0x80000, "win": 0x40000}  # kCGEventFlagMask*
# How the shared key names read on a Mac (the buttons' second line and the key pickers)
LABEL = {"ctrl": "Cmd", "alt": "Opt", "win": "Ctrl", "insert": "Help", "delete": "Del", "backspace": "Delete"}

_cg = None


def _coregraphics():
    global _cg
    if _cg is None:
        _cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics") or
                          "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        for fn in ("CGPreflightPostEventAccess", "CGRequestPostEventAccess"):
            getattr(_cg, fn).restype = ctypes.c_bool
    return _cg


def allowed():
    """Whether this app may post input events (System Settings → Privacy & Security → Accessibility)."""
    try:
        return bool(_coregraphics().CGPreflightPostEventAccess())
    except (OSError, AttributeError):
        return True  # older than 10.15: there was no such check


def request_access():
    """Ask for the permission: macOS shows its own prompt the first time, and the app appears in
    the Accessibility list. Returns whether it is already granted."""
    try:
        return bool(_coregraphics().CGRequestPostEventAccess())
    except (OSError, AttributeError):
        return True


def open_settings():
    import subprocess
    subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])


def available():
    return Q is not None


# --------------------------------------------------------------------------- displays

_DISPLAYS = []  # [(pixel rect l, t, r, b), point origin (x, y), scale]


def monitors():
    """Displays in pixels, main display first. A display at global points (x, y) with scale s
    sits at (x*s, y*s): rectangles keep the arrangement and, with mixed scales, may leave gaps,
    which is fine because each one maps back on its own."""
    global _DISPLAYS
    if Q is None:
        return [(0, 0, 1920, 1080)]
    err, ids, n = Q.CGGetActiveDisplayList(16, None, None)
    if err or not n:
        return [(0, 0, 1920, 1080)]
    main = Q.CGMainDisplayID()
    found = []
    for d in sorted(ids[:n], key=lambda d: d != main):
        b = Q.CGDisplayBounds(d)
        mode = Q.CGDisplayCopyDisplayMode(d)
        scale = 1.0
        if mode is not None and Q.CGDisplayModeGetWidth(mode):
            scale = Q.CGDisplayModeGetPixelWidth(mode) / Q.CGDisplayModeGetWidth(mode)
        x, y, w, h = b.origin.x, b.origin.y, b.size.width, b.size.height
        rect = (int(round(x * scale)), int(round(y * scale)), int(round((x + w) * scale)), int(round((y + h) * scale)))
        found.append((rect, (x, y), scale))
    _DISPLAYS = found
    return [r for r, _, _ in found]


def to_points(px, py):
    """A pixel from monitors() -> global Quartz point."""
    if not _DISPLAYS:
        monitors()
    for (l, t, r, b), (ox, oy), s in _DISPLAYS:
        if l <= px < r and t <= py < b:
            return ox + (px - l) / s, oy + (py - t) / s
    if _DISPLAYS:  # off every display: the nearest edge of the main one
        (l, t, r, b), (ox, oy), s = _DISPLAYS[0]
        return ox + (min(max(px, l), r - 1) - l) / s, oy + (min(max(py, t), b - 1) - t) / s
    return float(px), float(py)


def to_pixels(x, y):
    if not _DISPLAYS:
        monitors()
    for (l, t, r, b), (ox, oy), s in _DISPLAYS:
        pl, pt = ox, oy
        if pl <= x < pl + (r - l) / s and pt <= y < pt + (b - t) / s:
            return int(round(l + (x - ox) * s)), int(round(t + (y - oy) * s))
    return int(round(x)), int(round(y))


def _post(ev):
    Q.CGEventPost(Q.kCGHIDEventTap, ev)


# --------------------------------------------------------------------------- pen

POINTER_PEN, POINTER_ERASER = 1, 3  # NSPointingDeviceType pen / eraser
DEVICE_ID = 0x5244   # any stable id: the proximity events and the points must agree on it
TILT_FULL = 60.0     # degrees sent as tilt 1.0 (Qt reads it back as tilt * 60)
TABLET_RANGE = 65535  # the absolute tablet coordinates the points also carry


class MacPen:
    """Virtual pen tablet: hover, tip, pressure, tilt and the eraser end. Takes the same Frames
    as rmtablet.WindowsPen (pressure 0..1024, tilt in degrees)."""

    PRESSURE_MAX = 1024

    def __init__(self, post=None):
        if Q is None:
            raise OSError("pyobjc's Quartz is missing")
        self._post = post or _post
        self.tool = None    # POINTER_PEN / POINTER_ERASER while in range
        self.touch = False
        self.serial = 0
        self.last = (0.0, 0.0)
        self.lock = threading.Lock()

    def _proximity(self, pointer, enter):
        ev = Q.CGEventCreate(None)
        Q.CGEventSetType(ev, Q.kCGEventTabletProximity)
        Q.CGEventSetLocation(ev, self.last)
        F = Q.CGEventSetIntegerValueField
        F(ev, Q.kCGTabletProximityEventVendorID, 0x2D1F)
        F(ev, Q.kCGTabletProximityEventTabletID, 1)
        F(ev, Q.kCGTabletProximityEventPointerID, pointer)
        F(ev, Q.kCGTabletProximityEventDeviceID, DEVICE_ID)
        F(ev, Q.kCGTabletProximityEventSystemTabletID, 1)
        F(ev, Q.kCGTabletProximityEventVendorPointerType, 0x0802 if pointer == POINTER_PEN else 0x080A)
        F(ev, Q.kCGTabletProximityEventVendorPointerSerialNumber, 1)
        F(ev, Q.kCGTabletProximityEventVendorUniqueID, 0x5244000 + pointer)
        # NX_TABLET_CAPABILITY_* (IOKit IOLLEvent.h): device id, abs x, abs y, buttons, tilt x, tilt y, pressure
        F(ev, Q.kCGTabletProximityEventCapabilityMask, 0x0001 | 0x0002 | 0x0004 | 0x0040 | 0x0080 | 0x0100 | 0x0400)
        F(ev, Q.kCGTabletProximityEventPointerType, pointer)
        F(ev, Q.kCGTabletProximityEventEnterProximity, 1 if enter else 0)
        self._post(ev)

    def _point(self, kind, xy, pressure, tilt_x, tilt_y, buttons):
        ev = Q.CGEventCreateMouseEvent(None, kind, xy, Q.kCGMouseButtonLeft)
        F, D = Q.CGEventSetIntegerValueField, Q.CGEventSetDoubleValueField
        F(ev, Q.kCGMouseEventSubtype, Q.kCGEventMouseSubtypeTabletPoint)
        if kind in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp):
            F(ev, Q.kCGMouseEventClickState, 1)
        D(ev, Q.kCGMouseEventPressure, pressure)
        F(ev, Q.kCGTabletEventDeviceID, DEVICE_ID)
        F(ev, Q.kCGTabletEventPointButtons, buttons)
        D(ev, Q.kCGTabletEventPointPressure, pressure)
        D(ev, Q.kCGTabletEventTiltX, tilt_x)
        D(ev, Q.kCGTabletEventTiltY, tilt_y)
        # the absolute tablet position, as a share of the whole desktop (some apps read it)
        F(ev, Q.kCGTabletEventPointX, int(xy[0] * 8) & 0x7FFFFFFF)
        F(ev, Q.kCGTabletEventPointY, int(xy[1] * 8) & 0x7FFFFFFF)
        self._post(ev)

    def send(self, f):
        global LAST_PEN
        with self.lock:
            xy = to_points(f.x, f.y)
            if "INRANGE" not in f.flags:  # leaving range
                if self.tool is not None:
                    if self.touch:
                        self._point(Q.kCGEventLeftMouseUp, self.last, 0.0, 0.0, 0.0, 0)
                    self._proximity(self.tool, False)
                self.tool, self.touch = None, False
                return
            self.last = xy
            LAST_PEN = (f.x, f.y)
            tool = POINTER_ERASER if f.eraser else POINTER_PEN
            if self.tool is not None and tool != self.tool:
                if self.touch:
                    self._point(Q.kCGEventLeftMouseUp, xy, 0.0, 0.0, 0.0, 0)
                self._proximity(self.tool, False)
                self.tool, self.touch = None, False
            if self.tool is None:
                self._proximity(tool, True)
                self.tool = tool
            touching = "INCONTACT" in f.flags
            p = min(1.0, max(0.0, f.pressure / self.PRESSURE_MAX)) if touching else 0.0
            tx = max(-1.0, min(1.0, f.tilt_x / TILT_FULL))
            ty = max(-1.0, min(1.0, f.tilt_y / TILT_FULL))
            if touching and not self.touch:
                kind = Q.kCGEventLeftMouseDown
            elif touching:
                kind = Q.kCGEventLeftMouseDragged
            elif self.touch:
                kind = Q.kCGEventLeftMouseUp
            else:
                kind = Q.kCGEventMouseMoved
            self._point(kind, xy, p, tx, ty, 1 if touching else 0)
            self.touch = touching

    def close(self):
        with self.lock:
            tool, touching = self.tool, self.touch
        if tool is not None:
            if touching:
                self._point(Q.kCGEventLeftMouseUp, self.last, 0.0, 0.0, 0.0, 0)
            self._proximity(tool, False)
        self.tool, self.touch = None, False


# --------------------------------------------------------------------------- keys and drags

class MacInput:
    """Keys and the left-button drag, with the modifiers held so far added to every event."""

    def __init__(self, post=None):
        self._post = post or _post
        self.mods = set()
        self.button = False

    def flags(self):
        f = 0
        for m in self.mods:
            f |= FLAG[m]
        return f

    def key(self, name, up):
        if name in FLAG:
            (self.mods.discard if up else self.mods.add)(name)
        ev = Q.CGEventCreateKeyboardEvent(None, KEYCODE[name], not up)
        Q.CGEventSetFlags(ev, self.flags())
        self._post(ev)

    def _mouse(self, kind, px, py):
        ev = Q.CGEventCreateMouseEvent(None, kind, to_points(px, py), Q.kCGMouseButtonLeft)
        Q.CGEventSetFlags(ev, self.flags())
        if kind in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp):
            Q.CGEventSetIntegerValueField(ev, Q.kCGMouseEventClickState, 1)
        self._post(ev)

    def move(self, px, py):
        self._mouse(Q.kCGEventLeftMouseDragged if self.button else Q.kCGEventMouseMoved, px, py)

    def press(self, down, px, py):
        self.button = down
        self._mouse(Q.kCGEventLeftMouseDown if down else Q.kCGEventLeftMouseUp, px, py)


_INPUT = None


def devices():
    global _INPUT
    if _INPUT is None:
        _INPUT = MacInput()
    return _INPUT


def cursor_pos():
    if Q is None:
        return 0, 0
    p = Q.CGEventGetLocation(Q.CGEventCreate(None))
    return to_pixels(p.x, p.y)


def active_window_center():
    """Centre of the frontmost app's front window in pixels, or None. Window bounds need no
    Screen Recording permission (only window titles do)."""
    if Q is None:
        return None
    try:
        from AppKit import NSWorkspace
        pid = NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
    except Exception:
        return None
    wins = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements,
                                        Q.kCGNullWindowID) or []
    for w in wins:  # front to back
        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0:
            b = w.get("kCGWindowBounds") or {}
            if b.get("Width", 0) > 50 and b.get("Height", 0) > 50:
                return to_pixels(b["X"] + b["Width"] / 2, b["Y"] + b["Height"] / 2)
    return None

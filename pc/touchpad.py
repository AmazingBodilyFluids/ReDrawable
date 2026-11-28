"""Touchpad finger mode: the tablet's touch screen works like a laptop touchpad.

One finger moves the cursor (relative, like a touchpad, not to where the finger is). A quick tap
clicks, a two-finger tap right-clicks, two fingers dragging up or down scroll. Tap, then touch
again and drag within a moment: the left button stays down for the drag (select, move windows).

Contacts come in as screen pixels (the pen's own mapping, so the tablet's rotation is already
applied); the output is a small pointer object (WinPointer / LinuxPointer below, or a fake in tests).
"""
import sys
import time

TAP_MS = 220          # a touch shorter than this that hardly moved is a tap
TAP_SLOP = 14         # screen pixels a tap may wander
DRAG_GAP_MS = 300     # touch again this soon after a tap and drag: the button stays down
SCROLL_PX = 40        # screen pixels of two-finger travel per wheel notch


class TouchPad:
    def __init__(self, out, clock=time.monotonic):
        self.out = out
        self.clock = clock
        self.speed = 1.0
        self.reset()
        self.last_tap = -1.0

    def reset(self):
        self.prev = {}        # id -> (x, y) last update
        self.t0 = None        # start of this touch (first finger down)
        self.max_n = 0
        self.travel = 0.0     # how far the fingers went this touch, in screen pixels
        self.frac = [0.0, 0.0]  # sub-pixel cursor travel carried to the next update
        self.scroll = 0.0
        self.dragging = False
        self.drag_armed = False

    def update(self, contacts):
        """contacts: {id: (x, y)} in screen pixels; {} = every finger up (or muted: no click then)."""
        now = self.clock()
        if not contacts:
            self._lift(now, muted=False)
            return
        n = len(contacts)
        if self.t0 is None:
            self.t0 = now
            self.drag_armed = n == 1 and 0 <= now - self.last_tap <= DRAG_GAP_MS / 1000
        self.max_n = max(self.max_n, n)
        same = [cid for cid in contacts if cid in self.prev]
        if same:
            dx = sum(contacts[c][0] - self.prev[c][0] for c in same) / len(same)
            dy = sum(contacts[c][1] - self.prev[c][1] for c in same) / len(same)
            self.travel += abs(dx) + abs(dy)
            if n == 1 and self.max_n == 1:
                if self.drag_armed and not self.dragging and self.travel > TAP_SLOP:
                    self.dragging = True
                    self.out.button("left", True)
                self._move(dx, dy)
            elif n == 2:
                self.scroll += dy
                notches = int(self.scroll / SCROLL_PX)
                if notches:
                    self.scroll -= notches * SCROLL_PX
                    self.out.wheel(notches)  # fingers down = content down, as on a touchpad
        self.prev = dict(contacts)

    def mute(self):
        """The pen came near or a palm landed: let go of everything, no click."""
        self._lift(self.clock(), muted=True)

    def _move(self, dx, dy):
        self.frac[0] += dx * self.speed
        self.frac[1] += dy * self.speed
        ix, iy = int(self.frac[0]), int(self.frac[1])
        if ix or iy:
            self.frac[0] -= ix
            self.frac[1] -= iy
            self.out.move(ix, iy)

    def _lift(self, now, muted):
        if self.t0 is not None:
            quick = (now - self.t0) * 1000 <= TAP_MS and self.travel <= TAP_SLOP
            if self.dragging:
                self.out.button("left", False)
            elif not muted and quick and self.max_n in (1, 2):
                btn = "left" if self.max_n == 1 else "right"
                self.out.button(btn, True)
                self.out.button(btn, False)
                self.last_tap = now if self.max_n == 1 else -1.0
        self.reset()

    def close(self):
        self.mute()


class WinPointer:
    """Mouse output through SendInput's mouse_event. Moves are absolute (cursor + delta), so
    Windows' pointer acceleration doesn't stack on top of the touchpad's own speed."""

    MOVE, ABSOLUTE, VIRTUALDESK, WHEEL = 0x1, 0x8000, 0x4000, 0x800
    BUTTONS = {"left": (0x2, 0x4), "right": (0x8, 0x10)}

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt
        self.u = ctypes.windll.user32
        self.wt, self.ctypes = wt, ctypes

    def move(self, dx, dy):
        p = self.wt.POINT()
        self.u.GetCursorPos(self.ctypes.byref(p))
        g = self.u.GetSystemMetrics
        l, t, w, h = g(76), g(77), g(78), g(79)
        x = min(max(p.x + dx, l), l + w - 1)
        y = min(max(p.y + dy, t), t + h - 1)
        ax = int((x - l) * 65535 / max(1, w - 1))
        ay = int((y - t) * 65535 / max(1, h - 1))
        self.u.mouse_event(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK, ax, ay, 0, 0)

    def button(self, name, down):
        self.u.mouse_event(self.BUTTONS[name][0 if down else 1], 0, 0, 0, 0)

    def wheel(self, notches):
        # positive wheel data scrolls up; fingers moving down (positive dy) should scroll down
        self.u.mouse_event(self.WHEEL, 0, 0, self.ctypes.c_uint32(-120 * notches & 0xFFFFFFFF).value, 0)


class LinuxPointer:
    """The same through ReDrawable's virtual mouse (linuxinput)."""

    def __init__(self, clock=time.monotonic):
        import linuxinput
        self.li = linuxinput
        self.dev = linuxinput.devices()
        self.clock = clock
        self.pos, self.at = None, 0.0

    def move(self, dx, dy):
        # Asking the compositor for the cursor is slow (a hyprctl call), so it is asked once per
        # stroke and the moves are added up here; the mouse or pen may have moved it in between.
        now = self.clock()
        if self.pos is None or now - self.at > 0.5:
            self.pos = self.li.cursor_pos()
        self.at = now
        self.dev.pointer()  # makes the virtual mouse once and learns the desktop's extent
        l, t, r, b = self.dev.box
        self.pos = (min(max(self.pos[0] + dx, l), r - 1), min(max(self.pos[1] + dy, t), b - 1))
        self.dev.move(*self.pos)

    def button(self, name, down):
        self.dev.press(name, down)

    def wheel(self, notches):
        self.dev.wheel(-notches)


def make_pointer():
    return LinuxPointer() if sys.platform.startswith("linux") else WinPointer()

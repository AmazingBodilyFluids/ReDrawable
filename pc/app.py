#!/usr/bin/env python3
"""
ReDrawable: the desktop app (pywebview + WebView2). Double-click "ReDrawable.bat".

The window is an HTML interface in web/; everything it does goes through Api below to the
headless Engine in core.py. A small splash window shows while the engine starts.
Needs: Python 3.10+, `pip install -r requirements.txt` (paramiko, pywebview).
"""
import base64
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import paths  # noqa: E402

if (sys.stderr is None or sys.executable.lower().endswith("pythonw.exe")
        or (sys.platform.startswith("linux") and not sys.stdout.isatty())):  # Linux: started from the app launcher
    # pythonw has no console: keep errors in a log (where: paths.log_dir)
    sys.stderr = sys.stdout = open(os.path.join(paths.log_dir(), "redrawable.log"), "a", buffering=1, encoding="utf-8")
    print(f"--- started {time.strftime('%Y-%m-%d %H:%M:%S')}")

import rmtablet as rt  # noqa: E402

# Per-monitor DPI awareness first (rt.monitors sets it): the Windows pen needs physical pixels,
# and it must be in place before any window exists.
MONITORS = rt.monitors()

# AppImage: its WebKitGTK was patched to start its helper processes from "usr//lib/...", a path
# relative to the working directory, so that has to be the AppImage's root (app.py lives in
# usr/share/redrawable/pc).
_APPROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
if os.path.isfile(os.path.join(_APPROOT, "usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/WebKitNetworkProcess")) and \
        os.path.isfile(os.path.join(_APPROOT, "usr/share/redrawable/pc/app.py")):
    os.chdir(_APPROOT)
    sys.__stderr__.write(f"AppImage: working directory {_APPROOT}\n")

if sys.platform.startswith("linux"):
    # The window's app id on Wayland / class on X11, which launchers and the dock match to the .desktop
    # file (otherwise it would be "app.py"). Set before GTK starts.
    try:
        from gi.repository import GLib
        GLib.set_prgname(os.environ.get("FLATPAK_ID") or "redrawable")
        GLib.set_application_name("ReDrawable")
    except Exception:
        pass
import webview  # noqa: E402

import penmask  # noqa: E402
from core import Engine, use_profile_config  # noqa: E402
from version import __version__  # noqa: E402

CONFIG = use_profile_config()

if sys.platform == "win32":
    import winextras

BG = "#060e17"
# Window background per theme (web/themes.css), shown before the page has painted
THEME_BG = {"default": BG, "graphite": "#101215", "ledger": "#f4f1e8", "intaglio": "#0e1a15"}
SPLASH_MAX_S = 7.0  # give up waiting for the splash animation after this
MAIN_TITLE = "ReDrawable"
SPLASH_TITLE = "ReDrawable starting"


def saved_setting(key, allowed, default):
    """One saved setting, read before the engine exists (the splash needs it at once)."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            val = json.load(f).get("gui", {}).get(key)
    except (OSError, ValueError):
        val = None
    return val if val in allowed else default


def saved_theme():
    return saved_setting("theme", THEME_BG, "intaglio")


def clear_backdrop(title):
    """Make a transparent pywebview window truly see-through on Windows 11: pywebview's transparent=True
    is not enough on WebView2. The system backdrop goes off (pywebview sets Mica on dark windows) and so
    does the accent policy, or Windows paints a frosted blur behind the page. Same recipe as the K
    splash. Call while the window is still hidden."""
    import ctypes
    u, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    hwnd = u.FindWindowW(None, title)
    if not hwnd:
        return
    dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(ctypes.c_int(1)), 4)  # DWMWA_SYSTEMBACKDROP_TYPE: none
    dwm.DwmSetWindowAttribute(hwnd, 3, ctypes.byref(ctypes.c_int(1)), 4)   # DWMWA_TRANSITIONS_FORCEDISABLED
    dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(1)), 4)  # DWMWA_WINDOW_CORNER_PREFERENCE: square, as the main window

    class Accent(ctypes.Structure):
        _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int), ("color", ctypes.c_uint), ("anim", ctypes.c_int)]

    class Wca(ctypes.Structure):
        _fields_ = [("attr", ctypes.c_int), ("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]

    pol = Accent(0, 0, 0, 0)  # ACCENT_DISABLED
    wca = Wca(19, ctypes.cast(ctypes.pointer(pol), ctypes.c_void_p), ctypes.sizeof(pol))  # WCA_ACCENT_POLICY
    u.SetWindowCompositionAttribute(hwnd, ctypes.byref(wca))


def place_window(title, width, height):
    """Size and centre a window on the primary display's work area, in physical pixels.

    pywebview's own width/height/x/y are unreliable once the process is per-monitor DPI aware
    (needed for the pen): on a 1080p laptop the window came up too large and pushed
    off-screen. So the size is set natively: the design size times the display scale,
    clamped to 94% of the work area (screen minus taskbar)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes as wt
    u = ctypes.windll.user32
    hwnd = u.FindWindowW(None, title)
    if not hwnd:
        return
    work = wt.RECT()
    u.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    try:
        scale = u.GetDpiForWindow(hwnd) / 96.0
    except Exception:
        scale = 1.0
    ww, wh = work.right - work.left, work.bottom - work.top
    w = min(int(width * scale), int(ww * 0.94))
    h = min(int(height * scale), int(wh * 0.94))
    x = work.left + (ww - w) // 2
    y = work.top + (wh - h) // 2
    u.SetWindowPos(hwnd, None, x, y, w, h, 0x0004 | 0x0010)  # SWP_NOZORDER | SWP_NOACTIVATE


class Api:
    """Everything the page may call (window.pywebview.api.*). Underscored members stay hidden."""

    def __init__(self):
        self._engine = None
        self._window = None
        self._tray = None
        self._resizer = winextras.Resizer(900, 600) if sys.platform == "win32" else None
        self._quitting = False
        self._closing = False
        self._told_tray = False
        self._ready = threading.Event()

    # ---- state
    def ready(self):
        return self._ready.is_set()

    def snapshot(self):
        return self._engine.snapshot() if self._engine else None

    def live(self):
        return self._engine.live() if self._engine else {"pen": None}

    def version(self):
        return __version__

    # ---- settings and actions
    def set(self, key, value):
        self._engine.set(key, value)
        if key == "theme" and self._tray:
            self._tray.back_color(THEME_BG.get(value, BG))
        return True

    def connect(self):
        self._engine.connect()

    def disconnect(self):
        self._engine.disconnect()

    def set_output(self, on):
        self._engine.set_output(on)

    def restart_screen(self):
        self._engine.restart_screen()

    def set_light(self, pct):
        self._engine.set_light(pct)

    def clear_ink(self):
        self._engine.companion.send("clear")

    def tablet_action(self, a):
        """A click on the preview's panel or mask strip: the same action the tablet sends for a tap there."""
        self._engine.tablet_action(str(a))

    def get_mask(self):
        """The pen mask as stored (before contrast): base64 of N x N bytes, and its version."""
        return {"b64": self._engine.pmask.b64(), "ver": self._engine.pmask.ver, "n": penmask.N}

    def set_mask(self, b64, place=None):
        return self._engine.set_mask(b64, place)

    def set_mask_source(self, data_url):
        return self._engine.set_mask_source(data_url)

    def mask_source(self):
        return self._engine.mask_source()

    # the sample masks in web/masks: as data URLs, because the page (a file:// page) can't read
    # its own files into a canvas
    def sample_masks(self):
        with open(os.path.join(HERE, "web", "masks", "index.json"), encoding="utf-8") as f:
            return json.load(f)

    def sample_mask(self, sid):
        if not any(m["id"] == sid for m in self.sample_masks()):
            return None
        with open(os.path.join(HERE, "web", "masks", sid + ".png"), "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

    # the Tablet screen page's picture: the images the tablet is sent
    def trace_image(self):
        return self._engine.trace_image()

    def mask_thumbs(self):
        return self._engine.mask_thumbs()

    def mask_op(self, name):
        self._engine.mask_op(name)

    def new_mask(self, name=None):
        return self._engine.new_mask(name)

    def pick_mask(self, mid):
        self._engine.pick_mask(mid)

    def rename_mask(self, mid, name):
        self._engine.rename_mask(mid, name)

    def delete_mask(self, mid):
        self._engine.delete_mask(mid)

    def set_position(self, key):
        self._engine.set_position(key)

    def start_calibration(self, mode):
        self._engine.start_calibration(mode)

    def cancel_calibration(self):
        self._engine.cancel_calibration()

    def reset_peak(self):
        self._engine.reset_peak()

    def set_wifi(self, on):
        return self._engine.set_wifi(bool(on))

    def install_key(self, password):
        return self._engine.install_key(password)

    def finish_onboarding(self):
        self._engine.finish_onboarding()

    def restart_onboarding(self):
        self._engine.set("onboarded", False)

    def setup_uinput(self):
        """Linux: install the uinput rule (password prompt), then try the pen again."""
        import linuxinput
        ok, msg = linuxinput.setup_uinput()
        if ok and self._engine and self._engine.connected and not self._engine.output_on:
            self._engine.set_output(True)
        return {"ok": ok, "msg": msg}

    def open_calibration_pdf(self):
        path = os.path.normpath(os.path.join(HERE, "..", "tablet", "calibration-landscape.pdf"))
        if sys.platform == "win32":
            os.startfile(os.path.dirname(path))  # noqa: S606 (opens the folder in Explorer)
        elif sys.platform.startswith("linux"):
            import subprocess
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return path

    def pick_trace_image(self):
        """File dialog for the tracing image; the chosen path, or None."""
        kinds = ("Images (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp)", "All files (*.*)")
        got = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=kinds)
        if not got:
            return None
        path = got[0] if isinstance(got, (list, tuple)) else got
        self._engine.set("trace_file", path)
        return path

    def open_url(self, url):
        if url.startswith("https://"):
            import webbrowser
            webbrowser.open(url)

    # ---- window chrome (the window is frameless; the page draws its own title bar)
    def win_minimize(self):
        self._window.minimize()

    def win_toggle_max(self):
        w = self._window
        if getattr(self, "_maxed", False):
            w.restore()
            self._maxed = False
        else:
            w.maximize()
            self._maxed = True
        return self._maxed

    def win_close(self):
        self._window.destroy()  # on_closing decides between the tray and quitting

    # The window has no frame, so the page's edge grips resize it (winextras.Resizer)
    def resize_start(self, edge):
        if self._resizer:
            self._resizer.start(str(edge))

    def resize_move(self):
        if self._resizer:
            self._resizer.move()

    def resize_end(self):
        if self._resizer:
            self._resizer.end()

    # ---- tray
    def _toggle_pen(self):
        if self._engine:
            self._engine.set_output(not self._engine.output_on)

    def _exit(self):
        self._quitting = True
        self._window.destroy()

    def _to_tray(self):
        """Close button with "close to tray" on: hide instead of quitting. True if it did."""
        if (self._quitting or not self._tray or not self._engine or not self._engine.cfg.get("close_to_tray")
                or (sys.platform == "win32" and not winextras.user_closing(self._window.native))):
            return False
        self._window.hide()
        if not self._told_tray:
            self._told_tray = True
            self._tray.balloon("ReDrawable is still running",
                               "It stays in the tray so the pen keeps working. Right-click the icon to exit.")
        return True


def already_running():
    """One ReDrawable at a time: two would mean two synthetic pens fighting over the cursor.
    A named mutex says whether another copy owns it; if so, ask it to show its window (it may be
    hidden in the tray), or bring an older copy's window forward."""
    if sys.platform.startswith("linux"):
        import fcntl
        import paths
        main.lock = open(os.path.join(paths.data_dir(), "running.lock"), "w")  # held until exit
        try:
            fcntl.flock(main.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except OSError:
            import linuxtray
            linuxtray.signal_show()  # it may be hidden in the tray
            return True
    if sys.platform != "win32":
        return False
    import ctypes
    k, u = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.windll.user32
    k.CreateMutexW.restype = ctypes.c_void_p
    taken = False
    # held until exit; the old name too, so a copy from before the rename and this one keep out of each other's way
    main.mutexes = []
    for name in ("Local\\ReDrawable.SingleInstance", "Local\\PaperTablet.SingleInstance"):
        main.mutexes.append(k.CreateMutexW(None, False, name))
        taken = taken or ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    if not taken:
        return False
    if winextras.signal_show():
        return True
    hwnd = u.FindWindowW(None, MAIN_TITLE) or u.FindWindowW(None, "Paper Tablet")
    if hwnd:
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
        u.SetForegroundWindow(hwnd)
    return True


def splash_wanted():
    """Windows always. Linux: not on tiling compositors (Hyprland, Sway, i3), which would tile the
    splash like any other window and shuffle the desktop for a second. REDRAWABLE_SPLASH=1 / 0 overrides."""
    force = os.environ.get("REDRAWABLE_SPLASH")
    if force in ("0", "1"):
        return force == "1"
    if sys.platform == "win32":
        return True
    return not any(os.environ.get(v) for v in ("HYPRLAND_INSTANCE_SIGNATURE", "SWAYSOCK", "I3SOCK"))


def main():
    if already_running():
        print("ReDrawable is already running; brought it to the front.", flush=True)
        return
    api = Api()
    theme = saved_theme()
    # The splash is one object on the bare desktop (web/splash.html). On Windows its window is transparent
    # and the exact size and place of the main window, so the object can grow into it; elsewhere, where
    # see-through windows depend on the desktop, it stays the small themed window.
    use_splash = splash_wanted()
    clear = sys.platform == "win32" and use_splash
    start_js = "start(%s)" % json.dumps({"theme": theme, "opaque": not clear})
    if clear:
        splash = webview.create_window(SPLASH_TITLE, os.path.join(HERE, "web", "splash.html"),
                                       width=1240, height=820, frameless=True, easy_drag=False,
                                       on_top=True, transparent=True, hidden=True, resizable=False)

        def show_splash():
            try:
                place_window(SPLASH_TITLE, 1240, 820)
                clear_backdrop(SPLASH_TITLE)
            except Exception as ex:
                print("splash backdrop:", repr(ex), flush=True)
            try:
                splash.show()
                splash.evaluate_js(start_js)
            except Exception as ex:
                print("splash failed to show:", repr(ex), flush=True)

        # pywebview shows a transparent window as soon as it starts loading, ignoring hidden=True. The flag
        # has done its work once the native window exists, so it is cleared there and the window shows
        # only when show_splash says so, already in place and see-through.
        if hasattr(splash.events, "before_show"):
            splash.events.before_show += lambda: setattr(splash, "transparent", False)
        splash.events.loaded += lambda: threading.Thread(target=show_splash, daemon=True).start()
    elif use_splash:
        splash = webview.create_window(SPLASH_TITLE, os.path.join(HERE, "web", "splash.html"),
                                       width=560, height=340, frameless=True, easy_drag=False,
                                       on_top=True, background_color=THEME_BG[theme], resizable=False)
        splash.events.loaded += lambda: splash.evaluate_js(start_js)
    else:
        splash = None
    window = webview.create_window(MAIN_TITLE, os.path.join(HERE, "web", "index.html"), js_api=api,
                                   width=1240, height=820, min_size=(900, 600),
                                   frameless=True, easy_drag=False, hidden=True, background_color=THEME_BG[theme])
    if splash and not clear:
        splash.events.shown += lambda: place_window(SPLASH_TITLE, 560, 340)
    api._window = window
    t0 = time.time()

    def notify():
        if api._closing:
            return  # the page is going away; the engine's last "disconnected" has nowhere to go
        if api._tray and api._engine:
            api._tray.update(api._engine.connected, api._engine.output_on)
        try:
            window.evaluate_js("window.onEngineChange && window.onEngineChange()")
        except Exception:
            pass

    def start_tray():
        try:
            api._tray = winextras.Tray(window.native, on_open=lambda: api._tray.show_window(),
                                       on_toggle=api._toggle_pen, on_exit=api._exit)
            api._resizer.hwnd = api._tray.hwnd
            winextras.listen_for_show(lambda: api._tray.call(api._tray.show_window))
        except Exception as ex:  # the app still works without a tray icon; it just quits on close
            print("tray icon failed:", repr(ex), flush=True)
            import ctypes
            api._resizer.hwnd = ctypes.windll.user32.FindWindowW(None, MAIN_TITLE)

    def start_linux_tray():
        import linuxtray
        try:  # a second start shows this window, tray or not
            linuxtray.listen_for_show(lambda: (api._tray.show_window() if api._tray else (
                setattr(window, "hidden", False), window.show())))
        except OSError as ex:
            print("show signal:", repr(ex), flush=True)
        why = linuxtray.available()
        if why:  # closing the window then quits, as there is nowhere to bring it back from
            print("no tray icon:", why, flush=True)
            return
        try:
            api._tray = linuxtray.Tray(window, on_open=lambda: api._tray.show_window(),
                                       on_toggle=api._toggle_pen, on_exit=api._exit)
        except Exception as ex:
            print("tray icon failed:", repr(ex), flush=True)

    def boot():
        try:
            api._engine = Engine(on_change=notify)
        except Exception as ex:  # show the problem instead of a silent exit
            print("engine failed to start:", repr(ex), flush=True)
            raise
        api._ready.set()
        # Let the splash object land (the page reports it) instead of cutting it off at a fixed time,
        # then have it grow over its whole window (or fade, where the window is not see-through).
        def splash_says(flag, until):
            while time.time() < until:
                try:
                    if splash.evaluate_js("window.%s === true" % flag):
                        return
                except Exception:
                    return
                time.sleep(0.05)

        if splash:
            splash_says("splashDone", t0 + SPLASH_MAX_S)
            time.sleep(0.35)  # a beat on the finished logo
            try:
                splash.evaluate_js("handoff()")
                splash_says("splashCovered", time.time() + 1.5)
            except Exception:
                pass
        place_window(MAIN_TITLE, 1240, 820)  # while still hidden, so it never shows at the wrong size
        if sys.platform != "win32":
            # pywebview's GTK show() hides the window again at once while its hidden flag is still set
            # (gtk.main_level() is 0 under Gtk.Application, checked with pywebview 6.2.1)
            window.hidden = False
        window.show()
        place_window(MAIN_TITLE, 1240, 820)
        if clear:  # the main window is now under the splash's field, the same size: fade the field away
            try:
                time.sleep(0.25)
                splash.evaluate_js("reveal()")
                time.sleep(0.5)
            except Exception:
                pass
        if sys.platform == "win32":
            start_tray()
        elif sys.platform.startswith("linux"):
            start_linux_tray()
        notify()
        try:
            if splash:
                splash.destroy()
        except Exception:
            pass

    def on_closing():
        if api._to_tray():
            return False  # cancels the close
        api._closing = True
        # A process that hangs on its way out keeps the single-instance lock, and every later start
        # then only "brings it to the front" (nothing shows). Whatever hangs, end it after 8 s.
        guard = threading.Timer(8.0, lambda: os._exit(0))
        guard.daemon = True  # a normal exit doesn't wait for it
        guard.start()
        tray, api._tray = api._tray, None
        if api._engine:
            api._engine.shutdown()
        if tray:
            tray.dispose()

    window.events.closing += on_closing
    webview.start(boot, debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()

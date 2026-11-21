"""Linux tray icon and "show the running copy" signal.

The tray is a StatusNotifierItem through libayatana-appindicator (GObject introspection), the kind
waybar (Omarchy), KDE and GNOME with the AppIndicator extension show. It lives in pywebview's GTK
main loop, so everything that touches GTK is handed over with GLib.idle_add.

Same calls as winextras.Tray where app.py uses them: update(connected, output), balloon(title, text),
show_window(), call(fn), back_color(c), dispose().
"""
import os
import socket
import subprocess
import threading

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
# In a Flatpak the tray (outside the sandbox) can't read the app's files: the icons are the ones the
# Flatpak exports to the system icon theme, named after the app id.
APP_ID = os.environ.get("FLATPAK_ID", "")
ICON_ON, ICON_OFF = (APP_ID, APP_ID + "-off") if APP_ID else ("redrawable", "redrawable-off")


def _gi():
    import gi
    for name in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(name, "0.1")
            gi.require_version("Gtk", "3.0")
            from gi.repository import GLib, Gtk
            mod = __import__("gi.repository", fromlist=[name])
            return getattr(mod, name), Gtk, GLib
        except (ValueError, ImportError):
            continue
    return None, None, None


def host_present():
    """Is there a tray to show the icon in? (a StatusNotifierWatcher on the session bus)"""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        out = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
                            GLib.Variant("(s)", ("org.kde.StatusNotifierWatcher",)), None,
                            Gio.DBusCallFlags.NONE, 1000, None)
        return bool(out.unpack()[0])
    except Exception:
        return False


def available():
    """Why there can't be a tray icon, or "" if there can."""
    ind, _, _ = _gi()
    if ind is None:
        return "libayatana-appindicator isn't installed (run linux/setup.sh again)"
    if not host_present():
        return "the desktop has no tray (on Omarchy: the waybar tray module)"
    return ""


class Tray:
    def __init__(self, window, on_open, on_toggle, on_exit):
        self.window, self.on_open, self.on_toggle, self.on_exit = window, on_open, on_toggle, on_exit
        self.ind = self.pen_item = None
        self._busy = False  # set while update() moves the check item, so it isn't taken as a click
        Ind, self.Gtk, self.GLib = _gi()
        done = threading.Event()
        err = []

        def build():
            try:
                Gtk = self.Gtk
                self.ind = Ind.Indicator.new("redrawable", ICON_OFF,
                                             Ind.IndicatorCategory.APPLICATION_STATUS)
                if not APP_ID:
                    self.ind.set_icon_theme_path(ICONS)
                self.ind.set_title("ReDrawable")
                self.ind.set_status(Ind.IndicatorStatus.ACTIVE)
                menu = Gtk.Menu()
                show = Gtk.MenuItem.new_with_label("Open ReDrawable")
                show.connect("activate", lambda *_: self.on_open())
                self.pen_item = Gtk.CheckMenuItem.new_with_label("Pen on")
                self.pen_item.connect("toggled", lambda *_: None if self._busy else self.on_toggle())
                quit_ = Gtk.MenuItem.new_with_label("Exit ReDrawable")
                quit_.connect("activate", lambda *_: self.on_exit())
                for it in (show, self.pen_item, Gtk.SeparatorMenuItem(), quit_):
                    menu.append(it)
                menu.show_all()
                self.ind.set_menu(menu)
                self.ind.set_secondary_activate_target(show)  # middle click opens the window
            except Exception as ex:
                err.append(ex)
            done.set()
            return False

        self.GLib.idle_add(build)
        if not done.wait(5):
            raise OSError("the GTK loop didn't build the tray icon")
        if err:
            raise err[0]

    def call(self, fn):
        self.GLib.idle_add(lambda: (fn(), False)[1])

    def show_window(self):
        self.window.hidden = False  # see app.py: pywebview's GTK show() honours the flag
        self.window.show()
        try:
            self.window.restore()
        except Exception:
            pass

    def update(self, connected, output):
        def apply():
            if not self.ind:
                return False
            self.ind.set_icon_full(ICON_ON if connected else ICON_OFF,
                                   "connected" if connected else "not connected")
            self._busy = True
            self.pen_item.set_active(bool(output))
            self.pen_item.set_sensitive(bool(connected))
            self._busy = False
            return False
        self.GLib.idle_add(apply)

    def balloon(self, title, text):
        try:
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                     "org.freedesktop.Notifications", "Notify",
                     GLib.Variant("(susssasa{sv}i)", ("ReDrawable", 0, APP_ID or os.path.join(ICONS, "redrawable.png"),
                                                      title, text, [], {}, 8000)),
                     None, Gio.DBusCallFlags.NONE, 2000, None, None, None)
        except Exception:
            pass

    def back_color(self, _c):
        pass

    def dispose(self):
        def gone():
            if self.ind:
                self.ind.set_status(0)  # PASSIVE
            return False
        self.GLib.idle_add(gone)


# ---- one copy at a time: a second start asks the first to show its window

def _sock_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(base, "redrawable-%d.sock" % os.getuid())


def signal_show():
    """Ask a running copy to show its window. True if one answered."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(2)
        s.connect(_sock_path())
        s.sendall(b"show\n")
        return True
    except OSError:
        return False
    finally:
        s.close()


def listen_for_show(on_show):
    path = _sock_path()
    try:
        os.unlink(path)
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o600)
    srv.listen(2)

    def loop():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            with c:
                try:
                    if c.recv(16).startswith(b"show"):
                        on_show()
                except OSError:
                    pass
    threading.Thread(target=loop, daemon=True, name="show-listener").start()
    return srv

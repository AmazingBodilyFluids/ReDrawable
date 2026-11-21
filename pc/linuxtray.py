"""Linux tray icon and "show the running copy" signal.

The tray icon is a StatusNotifierItem (the D-Bus protocol waybar on Omarchy, KDE, and GNOME with the
AppIndicator extension show), written here directly on GLib's D-Bus instead of through
libayatana-appindicator. Ayatana marks its icon as "menu only", so every click just opens the menu;
this one takes clicks itself: a double click opens the window, right click shows the menu (served as
com.canonical.dbusmenu), middle click opens the window too. The icon goes over D-Bus as pixels, so
the tray can draw it from inside a Flatpak or an AppImage as well. No extra library needed.

Same calls as winextras.Tray where app.py uses them: update(connected, output), balloon(title, text),
show_window(), call(fn), back_color(c), dispose().
"""
import os
import socket
import threading
import time

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
APP_ID = os.environ.get("FLATPAK_ID", "")
DOUBLE_S = 0.5  # two clicks within this are a double click

SNI_XML = """<node>
<interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="WindowId" type="i" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionIconName" type="s" access="read"/>
  <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
  <property name="OverlayIconName" type="s" access="read"/>
  <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
  <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
  <signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewToolTip"/>
  <signal name="NewStatus"><arg name="status" type="s"/></signal>
</interface>
</node>"""

MENU_XML = """<node>
<interface name="com.canonical.dbusmenu">
  <property name="Version" type="u" access="read"/>
  <property name="TextDirection" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconThemePath" type="as" access="read"/>
  <method name="GetLayout">
    <arg type="i" name="parentId" direction="in"/><arg type="i" name="recursionDepth" direction="in"/>
    <arg type="as" name="propertyNames" direction="in"/>
    <arg type="u" name="revision" direction="out"/><arg type="(ia{sv}av)" name="layout" direction="out"/>
  </method>
  <method name="GetGroupProperties">
    <arg type="ai" name="ids" direction="in"/><arg type="as" name="propertyNames" direction="in"/>
    <arg type="a(ia{sv})" name="properties" direction="out"/>
  </method>
  <method name="GetProperty">
    <arg type="i" name="id" direction="in"/><arg type="s" name="name" direction="in"/>
    <arg type="v" name="value" direction="out"/>
  </method>
  <method name="Event">
    <arg type="i" name="id" direction="in"/><arg type="s" name="eventId" direction="in"/>
    <arg type="v" name="data" direction="in"/><arg type="u" name="timestamp" direction="in"/>
  </method>
  <method name="EventGroup">
    <arg type="a(isvu)" name="events" direction="in"/><arg type="ai" name="idErrors" direction="out"/>
  </method>
  <method name="AboutToShow"><arg type="i" name="id" direction="in"/><arg type="b" name="needUpdate" direction="out"/></method>
  <method name="AboutToShowGroup">
    <arg type="ai" name="ids" direction="in"/><arg type="ai" name="updatesNeeded" direction="out"/>
    <arg type="ai" name="idErrors" direction="out"/>
  </method>
  <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
  <signal name="LayoutUpdated"><arg type="u" name="revision"/><arg type="i" name="parent"/></signal>
</interface>
</node>"""


def _pixmaps(name):
    """The icon as SNI pixmaps: (width, height, ARGB32 bytes in network order), a few sizes."""
    try:
        from gi.repository import GdkPixbuf
        src = GdkPixbuf.Pixbuf.new_from_file(os.path.join(ICONS, name + ".png"))
    except Exception:
        return []
    out = []
    for size in (16, 22, 24, 32, 48, 64):
        pb = src.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        if not pb.get_has_alpha():
            pb = pb.add_alpha(False, 0, 0, 0)
        px, stride = pb.get_pixels(), pb.get_rowstride()
        data = bytearray()
        for y in range(size):
            row = px[y * stride: y * stride + size * 4]
            for x in range(0, size * 4, 4):
                r, g, b, a = row[x:x + 4]
                data += bytes((a, r, g, b))
        out.append((size, size, bytes(data)))
    return out


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
    if not host_present():
        return "the desktop has no tray (on Omarchy: the waybar tray module)"
    return ""


class Tray:
    PATH, MENU_PATH = "/StatusNotifierItem", "/MenuBar"
    # menu items: id -> (label, kind)
    ITEMS = [(1, "Open ReDrawable", "open"), (2, "Pen on", "pen"), (3, "", "sep"), (4, "Exit ReDrawable", "exit")]

    def __init__(self, window, on_open, on_toggle, on_exit):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.window, self.on_open, self.on_toggle, self.on_exit = window, on_open, on_toggle, on_exit
        self.connected = self.output = False
        self.status = "Active"
        self.revision = 1
        self.last_click = 0.0
        self.icons = {"on": _pixmaps("redrawable"), "off": _pixmaps("redrawable-off")}
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.reg = [self.bus.register_object(self.PATH, sni, self._sni_call, self._sni_prop, None),
                    self.bus.register_object(self.MENU_PATH, menu, self._menu_call, self._menu_prop, None)]
        self.bus.call_sync("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher",
                           "RegisterStatusNotifierItem", GLib.Variant("(s)", (self.bus.get_unique_name(),)),
                           None, Gio.DBusCallFlags.NONE, 3000, None)

    # ---- StatusNotifierItem
    def _sni_prop(self, conn, sender, path, iface, name):
        V = self.GLib.Variant
        tip = "ReDrawable: " + ("connected" if self.connected else "not connected")
        icon = self.icons["on" if self.connected else "off"]
        return {
            "Category": V("s", "ApplicationStatus"), "Id": V("s", "redrawable"), "Title": V("s", "ReDrawable"),
            "Status": V("s", self.status), "WindowId": V("i", 0), "IconName": V("s", ""),
            "IconPixmap": V("a(iiay)", icon), "AttentionIconName": V("s", ""), "AttentionIconPixmap": V("a(iiay)", []),
            "OverlayIconName": V("s", ""), "OverlayIconPixmap": V("a(iiay)", []),
            "ToolTip": V("(sa(iiay)ss)", ("", [], "ReDrawable", tip)),
            "ItemIsMenu": V("b", False), "Menu": V("o", self.MENU_PATH),
        }.get(name)

    def _sni_call(self, conn, sender, path, iface, method, params, inv):
        if method == "Activate":  # left click: a double click opens the window
            now = time.monotonic()
            if now - self.last_click < DOUBLE_S:
                self.last_click = 0.0
                self._off_loop(self.on_open)
            else:
                self.last_click = now
        elif method == "SecondaryActivate":  # middle click
            self._off_loop(self.on_open)
        inv.return_value(None)

    # ---- the menu (com.canonical.dbusmenu)
    def _item_props(self, i, label, kind):
        V = self.GLib.Variant
        if kind == "sep":
            return {"type": V("s", "separator")}
        p = {"label": V("s", label), "enabled": V("b", kind != "pen" or self.connected), "visible": V("b", True)}
        if kind == "pen":
            p["toggle-type"] = V("s", "checkmark")
            p["toggle-state"] = V("i", 1 if self.output else 0)
        return p

    def _layout(self):
        V = self.GLib.Variant
        kids = [V("(ia{sv}av)", (i, self._item_props(i, label, kind), [])) for i, label, kind in self.ITEMS]
        return (0, {"children-display": V("s", "submenu")}, kids)

    def _menu_prop(self, conn, sender, path, iface, name):
        V = self.GLib.Variant
        return {"Version": V("u", 3), "TextDirection": V("s", "ltr"), "Status": V("s", "normal"),
                "IconThemePath": V("as", [])}.get(name)

    def _menu_call(self, conn, sender, path, iface, method, params, inv):
        V = self.GLib.Variant
        if method == "GetLayout":
            inv.return_value(V("(u(ia{sv}av))", (self.revision, self._layout())))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0]
            out = [(i, self._item_props(i, label, kind)) for i, label, kind in self.ITEMS if not ids or i in ids]
            inv.return_value(V("(a(ia{sv}))", (out,)))
        elif method == "GetProperty":
            i, name = params.unpack()
            props = next((self._item_props(*it) for it in self.ITEMS if it[0] == i), {})
            inv.return_value(V("(v)", (props.get(name, V("s", "")),)))
        elif method == "Event":
            i, event = params.unpack()[:2]
            if event == "clicked":
                self._clicked(i)
            inv.return_value(None)
        elif method == "EventGroup":
            for i, event, _d, _t in params.unpack()[0]:
                if event == "clicked":
                    self._clicked(i)
            inv.return_value(V("(ai)", ([],)))
        elif method == "AboutToShow":
            inv.return_value(V("(b)", (False,)))
        elif method == "AboutToShowGroup":
            inv.return_value(V("(aiai)", ([], [])))
        else:
            inv.return_value(None)

    def _clicked(self, i):
        kind = next((k for j, _l, k in self.ITEMS if j == i), "")
        fn = {"open": self.on_open, "pen": self.on_toggle, "exit": self.on_exit}.get(kind)
        if fn:
            self._off_loop(fn)

    @staticmethod
    def _off_loop(fn):
        """D-Bus calls arrive on the GTK loop; pywebview's show() only takes effect from another thread."""
        threading.Thread(target=fn, daemon=True).start()

    def _emit(self, path, iface, signal, args=None):
        try:
            self.bus.emit_signal(None, path, iface, signal, args)
        except Exception:
            pass

    # ---- what app.py calls
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
        connected, output = bool(connected), bool(output)
        if (connected, output) == (self.connected, self.output):
            return
        icon_changed = connected != self.connected
        self.connected, self.output = connected, output
        self.revision += 1

        def emit():
            if icon_changed:
                self._emit(self.PATH, "org.kde.StatusNotifierItem", "NewIcon")
                self._emit(self.PATH, "org.kde.StatusNotifierItem", "NewToolTip")
            self._emit(self.MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                       self.GLib.Variant("(ui)", (self.revision, 0)))
            return False
        self.GLib.idle_add(emit)

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
        self.status = "Passive"
        for r in self.reg:
            try:
                self.bus.unregister_object(r)
            except Exception:
                pass
        self.reg = []


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

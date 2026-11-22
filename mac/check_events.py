"""End-to-end check of the Mac output on a real macOS (CI runner or a Mac): opens a window, sends
a pen stroke, an eraser stroke, keys and a drag into it through pc/macinput.py, and reports what
the window actually received from the window server, as an app would see it (NSEvent).

    python3 mac/check_events.py            # prints a JSON report, exit 1 if a check failed

Needs pyobjc (Cocoa + Quartz) and the Accessibility permission for the process that runs it.
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc"))

import AppKit as A  # noqa: E402
import Quartz as Q  # noqa: E402

import keys  # noqa: E402
import macinput  # noqa: E402
from rmtablet import Frame  # noqa: E402

GOT = []
W, H, LEFT, TOP = 640, 420, 120, 160  # window in global points, top-left origin


def record(e):
    t = e.type()
    row = {"type": int(t)}
    if t in (A.NSEventTypeLeftMouseDown, A.NSEventTypeLeftMouseDragged, A.NSEventTypeLeftMouseUp,
             A.NSEventTypeMouseMoved, A.NSEventTypeTabletPoint):
        row["subtype"] = int(e.subtype())
        row["pressure"] = round(float(e.pressure()), 4)
        if e.subtype() == A.NSEventSubtypeTabletPoint or t == A.NSEventTypeTabletPoint:
            tl = e.tilt()
            row["tilt"] = [round(float(tl.x), 4), round(float(tl.y), 4)]
            row["device"] = int(e.deviceID())
        p = e.locationInWindow()
        row["xy"] = [round(float(p.x), 1), round(float(p.y), 1)]
    elif t == A.NSEventTypeTabletProximity:
        row.update(enter=bool(e.isEnteringProximity()), pointer=int(e.pointingDeviceType()),
                   device=int(e.deviceID()), caps=int(e.capabilityMask()))
    elif t in (A.NSEventTypeKeyDown, A.NSEventTypeKeyUp, A.NSEventTypeFlagsChanged):
        row["code"] = int(e.keyCode())
        row["flags"] = int(e.modifierFlags()) & 0xFFFF0000
        if t != A.NSEventTypeFlagsChanged:
            row["chars"] = e.charactersIgnoringModifiers()
    GOT.append(row)
    return e


def px(x, y):
    """Window-relative points -> the pixels macinput's frames use."""
    return macinput.to_pixels(LEFT + x, TOP + y)


def send_all():
    time.sleep(2.0)
    pen = macinput.MacPen()

    def f(flags, x, y, p=0, tx=0, ty=0, eraser=False):
        X, Y = px(x, y)
        pen.send(Frame(flags=set(flags), x=X, y=Y, pressure=p, tilt_x=tx, tilt_y=ty, eraser=eraser))
        time.sleep(0.02)

    # pen: hover in, touch down, drag with rising pressure and a fixed tilt, lift, leave
    for i in range(3):
        f({"INRANGE", "UPDATE"}, 100 + i * 5, 100, tx=30, ty=-20)
    f({"INRANGE", "INCONTACT", "DOWN"}, 120, 110, p=100, tx=30, ty=-20)
    for i in range(1, 10):
        f({"INRANGE", "INCONTACT", "UPDATE"}, 120 + i * 20, 110 + i * 5, p=100 * i + 100, tx=30, ty=-20)
    f({"INRANGE", "UP"}, 320, 160, tx=30, ty=-20)
    f({"UPDATE"}, 320, 160)
    # eraser end
    f({"INRANGE", "UPDATE"}, 200, 250, eraser=True)
    f({"INRANGE", "INCONTACT", "DOWN"}, 200, 250, p=512, eraser=True)
    f({"INRANGE", "INCONTACT", "UPDATE"}, 260, 260, p=512, eraser=True)
    f({"INRANGE", "UP"}, 260, 260, eraser=True)
    f({"UPDATE"}, 260, 260, eraser=True)
    time.sleep(0.3)
    k = keys.Keys()
    for spec in ("ctrl+z", "b", "shift+]", "alt+e", "win+f1"):
        k.combo(spec)
        time.sleep(0.15)
    m = keys.make_mouse()
    m.begin_at(*px(400, 300))
    for i in range(5):
        m.move(i * 10, i * 4)
        time.sleep(0.03)
    m.end()
    time.sleep(1.0)
    from PyObjCTools import AppHelper

    def stop():  # stop (not terminate, which would exit before the report), then wake the loop
        A.NSApp.stop_(None)
        A.NSApp.postEvent_atStart_(A.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            A.NSEventTypeApplicationDefined, (0, 0), 0, 0, 0, None, 0, 0, 0), True)
    AppHelper.callAfter(stop)


def checks():
    tab = [g for g in GOT if g.get("subtype") == 1]
    prox = [g for g in GOT if g["type"] == A.NSEventTypeTabletProximity]
    downs = [g for g in tab if g["type"] in (A.NSEventTypeLeftMouseDown, A.NSEventTypeLeftMouseDragged)]
    pen_drag = [g for g in downs if g.get("tilt") and abs(g["tilt"][0] - 0.5) < 0.02]
    keys_down = [g for g in GOT if g["type"] == A.NSEventTypeKeyDown]
    by = {g.get("chars"): g for g in keys_down}
    plain = [g for g in GOT if g["type"] == A.NSEventTypeLeftMouseDragged and g.get("subtype") == 0]
    pressures = [g["pressure"] for g in pen_drag]
    return {
        "proximity: pen enters": any(p["enter"] and p["pointer"] == 1 for p in prox),
        "proximity: pen leaves": any(not p["enter"] and p["pointer"] == 1 for p in prox),
        "proximity: eraser enters": any(p["enter"] and p["pointer"] == 3 for p in prox),
        "proximity and points share a device id": bool(tab) and {p["device"] for p in prox} >= {g["device"] for g in tab if "device" in g},
        "hover arrives as tablet mouse-moved": any(g["type"] == A.NSEventTypeMouseMoved for g in tab),
        "stroke arrives as tablet down + dragged": len(pen_drag) >= 5,
        "pressure rises along the stroke (0.1 .. 1.0)": len(pressures) >= 5 and pressures == sorted(pressures)
            and abs(pressures[0] - 100 / 1024) < 0.02 and pressures[-1] > 0.9,
        "tilt x = 30 deg -> 0.5, y = -20 deg -> -0.333": bool(pen_drag) and all(abs(g["tilt"][1] + 1 / 3) < 0.02 for g in pen_drag),
        "eraser stroke has pressure 0.5": any(g.get("tilt") == [0.0, 0.0] and abs(g["pressure"] - 0.5) < 0.02 for g in downs),
        "ctrl+z -> z with Command": "z" in by and by["z"]["flags"] & A.NSEventModifierFlagCommand != 0,
        "b -> b, no modifier": "b" in by and by["b"]["flags"] & 0x1F0000 == 0,
        # charactersIgnoringModifiers keeps Shift (it reads "}"), so the key code is checked
        "shift+] -> ] key with Shift": any(g["code"] == 0x1E and g["flags"] & A.NSEventModifierFlagShift for g in keys_down),
        "alt+e -> e with Option": "e" in by and by["e"]["flags"] & A.NSEventModifierFlagOption != 0,
        "win+f1 -> F1 with Control": any(g["code"] == 0x7A and g["flags"] & A.NSEventModifierFlagControl for g in keys_down),
        "pan drag arrives as a plain left drag": len(plain) >= 3,
    }


def main():
    app = A.NSApplication.sharedApplication()
    app.setActivationPolicy_(A.NSApplicationActivationPolicyRegular)
    screen_h = A.NSScreen.screens()[0].frame().size.height
    rect = A.NSMakeRect(LEFT, screen_h - TOP - H, W, H)
    win = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, A.NSWindowStyleMaskBorderless, A.NSBackingStoreBuffered, False)
    win.setAcceptsMouseMovedEvents_(True)
    win.setLevel_(A.NSFloatingWindowLevel)
    win.setBackgroundColor_(A.NSColor.whiteColor())
    win.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    A.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(A.NSEventMaskAny, record)
    threading.Thread(target=send_all, daemon=True).start()
    app.run()
    result = checks()
    report = {"post_access": macinput.allowed(), "monitors_px": macinput.monitors(),
              "displays": [[list(r), list(o), s] for r, o, s in macinput._DISPLAYS],
              "checks": result, "events": GOT}
    print(json.dumps(report, indent=1, default=str))
    print("\n".join(("PASS " if v else "FAIL ") + k for k, v in result.items()))
    sys.exit(0 if all(result.values()) else 1)


if __name__ == "__main__":
    main()

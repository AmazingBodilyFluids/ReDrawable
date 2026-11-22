"""The Mac pen's event sequence (macinput.MacPen) against a stand-in for pyobjc's Quartz, so it
runs anywhere. What the window server and apps make of the events is checked on a real macOS by
mac/check_events.py (CI)."""
import types
import unittest

import macinput
from rmtablet import Frame


class FakeQuartz(types.SimpleNamespace):
    """Records every event as a dict of the fields set on it."""

    def __init__(self):
        names = ["kCGEventTabletProximity", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGEventLeftMouseDragged",
                 "kCGEventMouseMoved", "kCGMouseButtonLeft", "kCGMouseEventSubtype", "kCGEventMouseSubtypeTabletPoint",
                 "kCGMouseEventClickState", "kCGMouseEventPressure", "kCGTabletEventDeviceID", "kCGTabletEventPointButtons",
                 "kCGTabletEventPointPressure", "kCGTabletEventTiltX", "kCGTabletEventTiltY", "kCGTabletEventPointX",
                 "kCGTabletEventPointY", "kCGHIDEventTap"]
        names += ["kCGTabletProximityEvent" + n for n in (
            "VendorID", "TabletID", "PointerID", "DeviceID", "SystemTabletID", "VendorPointerType",
            "VendorPointerSerialNumber", "VendorUniqueID", "CapabilityMask", "PointerType", "EnterProximity")]
        super().__init__(**{n: n for n in names})

    def CGEventCreate(self, src):
        return {}

    def CGEventCreateMouseEvent(self, src, kind, xy, button):
        return {"type": kind, "xy": xy}

    def CGEventSetType(self, ev, t):
        ev["type"] = t

    def CGEventSetLocation(self, ev, xy):
        ev["xy"] = xy

    def CGEventSetIntegerValueField(self, ev, k, v):
        ev[k] = v

    CGEventSetDoubleValueField = CGEventSetIntegerValueField


class MacPenTest(unittest.TestCase):
    def setUp(self):
        self.q, self.old = FakeQuartz(), macinput.Q
        macinput.Q = self.q
        macinput._DISPLAYS = [((0, 0, 2880, 1800), (0.0, 0.0), 2.0)]  # a Retina laptop: 1440 x 900 points
        self.sent = []
        self.pen = macinput.MacPen(post=self.sent.append)

    def tearDown(self):
        macinput.Q = self.old
        macinput._DISPLAYS = []

    def f(self, flags, x=100, y=200, p=0, tx=0, ty=0, eraser=False):
        self.pen.send(Frame(flags=set(flags), x=x, y=y, pressure=p, tilt_x=tx, tilt_y=ty, eraser=eraser))

    def kinds(self):
        return [e["type"] if e["type"] != "kCGEventTabletProximity" else
                ("in" if e["kCGTabletProximityEventEnterProximity"] else "out") + str(e["kCGTabletProximityEventPointerType"])
                for e in self.sent]

    def test_stroke(self):
        self.f({"INRANGE", "UPDATE"}, tx=30, ty=-20)
        self.f({"INRANGE", "INCONTACT", "DOWN"}, p=512, tx=30, ty=-20)
        self.f({"INRANGE", "INCONTACT", "UPDATE"}, x=300, p=1024)
        self.f({"INRANGE", "UP"}, x=300)
        self.f({"UPDATE"}, x=300)
        self.assertEqual(self.kinds(), ["in1", "kCGEventMouseMoved", "kCGEventLeftMouseDown", "kCGEventLeftMouseDragged",
                                        "kCGEventLeftMouseUp", "out1"])
        hover, down, drag = self.sent[1:4]
        self.assertEqual(hover["xy"], (50.0, 100.0))  # pixels back to points
        self.assertEqual(hover["kCGTabletEventPointPressure"], 0.0)
        self.assertAlmostEqual(down["kCGTabletEventPointPressure"], 0.5)
        self.assertAlmostEqual(down["kCGMouseEventPressure"], 0.5)
        self.assertEqual(drag["kCGTabletEventPointPressure"], 1.0)
        self.assertAlmostEqual(hover["kCGTabletEventTiltX"], 0.5)
        self.assertAlmostEqual(hover["kCGTabletEventTiltY"], -1 / 3)
        self.assertEqual(down["kCGMouseEventSubtype"], "kCGEventMouseSubtypeTabletPoint")
        self.assertEqual(down["kCGMouseEventClickState"], 1)
        ids = {e.get("kCGTabletEventDeviceID") or e.get("kCGTabletProximityEventDeviceID") for e in self.sent}
        self.assertEqual(ids, {macinput.DEVICE_ID})

    def test_switching_to_the_eraser_leaves_range_first(self):
        self.f({"INRANGE", "INCONTACT", "DOWN"}, p=300)
        self.f({"INRANGE", "UPDATE"}, eraser=True)
        self.assertEqual(self.kinds(), ["in1", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "out1", "in3",
                                        "kCGEventMouseMoved"])

    def test_close_lifts_and_leaves(self):
        self.f({"INRANGE", "INCONTACT", "DOWN"}, p=300)
        self.pen.close()
        self.assertEqual(self.kinds()[-2:], ["kCGEventLeftMouseUp", "out1"])

    def test_tilt_is_clamped(self):
        self.f({"INRANGE", "UPDATE"}, tx=90, ty=-90)
        self.assertEqual((self.sent[1]["kCGTabletEventTiltX"], self.sent[1]["kCGTabletEventTiltY"]), (1.0, -1.0))


class Displays(unittest.TestCase):
    def test_points_and_pixels_round_trip_on_mixed_scales(self):
        # a Retina laptop and a 1080p screen to its right, and one above it
        macinput._DISPLAYS = macinput.layout([(0, 0, 1440, 900, 2.0), (1440, 0, 1920, 1080, 1.0), (0, -1080, 1920, 1080, 1.0)])
        rects = [r for r, _, _ in macinput._DISPLAYS]
        self.assertEqual(rects, [(0, 0, 2880, 1800), (2880, 0, 4800, 1080), (0, -2160, 1920, -1080)])
        for i, a in enumerate(rects):  # no overlaps
            for b in rects[i + 1:]:
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b))
        try:
            self.assertEqual(macinput.to_points(2879, 1799), (1439.5, 899.5))
            self.assertEqual(macinput.to_points(100, -2000), (100.0, -920.0))
            self.assertEqual(macinput.to_points(3000, 10), (1560.0, 10.0))
            self.assertEqual(macinput.to_pixels(1560.0, 10.0), (3000, 10))
            self.assertEqual(macinput.to_pixels(100.25, 50.5), (200, 101))
        finally:
            macinput._DISPLAYS = []


if __name__ == "__main__":
    unittest.main()

// The companion UI. Panel is 1620 x 2160 portrait; `view` is rotated to how the tablet sits.
// Black and white only: greys ghost in the fast pen waveform.
extern const char *COMPANION_QML;
const char *COMPANION_QML = R"QML(
import QtQuick

Window {
    id: win
    // Sized from the screen as in reMarkable's epaper example: FullScreen alone left the window
    // 0x0 on the device, so nothing was ever drawn.
    width: Screen.width
    height: Screen.height
    visible: true
    color: "white"
    property int rot: 0
    property string mode: "blank"
    property int nextTarget: 0
    property var area: [0, 0, 1, 1]
    property string status: "Connected to PC"
    property var last: null
    property var stroke: null      // segments of the stroke being drawn
    property int fadeMs: 1500      // how long a finished stroke stays; 0 keeps it ("fade MS")
    property var lastStroke: null  // the stroke that just ended, in case the PC snaps it
    property var held: null        // snapped shape while the pen is still down
    property bool penDown: false

    // side panels: one on either side, both, or none. Buttons 0-15 are the left panel's, 16-31 the right's.
    property string panelSide: "left"   // left | right | both | off
    property real panelFrac: 0.14       // of the view width
    // buttons across a panel: 2, or 1 on a small tablet (the Move), where the panels are half as
    // wide and their buttons and tiles scroll with a finger drag ("cols 1" from the PC)
    property int cols: 2
    readonly property bool narrow: cols === 1
    property var scrolls: ({left: 0, right: 0, mask: 0, trace: 0})   // px scrolled, narrow only
    property bool panelOpen: true       // the left panel; folded away with the tab in its top corner
    property bool panelOpenR: true      // the right panel
    property bool gesturesOn: true
    property bool penOut: true          // states the PC reports ("state pen 1 snap 0")
    property bool snapOn: true
    property var latched: ({})          // hold buttons locked down, by index
    property int pressing: -1           // button under a finger or the pen right now
    property real holdStart: 0
    property bool keepLatch: false
    property string toast: ""
    property real penSeen: 0            // last time the pen was in range (palm rejection)
    property int penBtn: -1             // what the pen tip is on in a panel (-2 / -6 = left / right tab, 99 = nothing)
    readonly property real tabS: 84
    readonly property bool panelOnL: mode === "ink" && (panelSide === "left" || panelSide === "both")
    readonly property bool panelOnR: mode === "ink" && (panelSide === "right" || panelSide === "both")
    readonly property bool panelOn: panelOnL || panelOnR
    readonly property real panelPx: panelFrac * view.width
    // "panelshow K M T" (the PC's Button setting for each kind of panel: shortcuts, mask, tracing image):
    //   hover: with every panel on a side folded, that kind's corner tab is hidden until the pen
    //          hovers along the edge a moment; a pen tap on it opens the panel. Hidden, the corner
    //          is drawing area.
    //   tap:   only fingers work the tab and the panel; the pen draws through them
    property string panelShow: "always"
    property string maskShow: "always"
    property string traceShow: "always"
    property bool peekL: false           // hover: this side's hidden tabs are showing
    property bool peekR: false
    property string hoverSide: ""        // where the pen hovers, waiting for hoverTimer
    function peeked(s) { return s === "right" ? peekR : peekL }
    // ---- the three kinds of panel: "keys" (shortcuts, one a side), "mask", "trace" (tracing images).
    // A side's kinds each have a corner tab, in this order from the corner, and open in the same
    // place. Only one kind is open at a time: opening one folds the others.
    function kinds(s) {
        var k = []
        if (s === "right" ? panelOnR : panelOnL) k.push("keys")
        if (mode === "ink" && stripAvail && stripSide === s) k.push("mask")
        if (mode === "ink" && tstripAvail && tstripSide === s) k.push("trace")
        return k
    }
    function kindOpen(k, s) { return k === "keys" ? sideOpen(s) : k === "mask" ? stripOpen : tstripOpen }
    function kindShow(k) { return k === "keys" ? panelShow : k === "mask" ? maskShow : traceShow }
    function openKind(s) {  // the kind open on this side, or ""
        var k = kinds(s)
        for (var i = 0; i < k.length; i++) if (kindOpen(k[i], s)) return k[i]
        return ""
    }
    function tabShown(k, s) { return kindShow(k) !== "hover" || openKind(s) !== "" || peeked(s) }
    function tabX(s, i) { return s === "right" ? view.width - (i + 1) * tabS : i * tabS }
    function tabAt(p) {  // the corner tab under p: {k, s}, or null
        if (p.y < 0 || p.y >= tabS) return null
        var sides = ["left", "right"]
        for (var j = 0; j < 2; j++) {
            var s = sides[j], k = kinds(s)
            var i = Math.floor((s === "right" ? view.width - p.x : p.x) / tabS)
            if (i >= 0 && i < k.length && tabShown(k[i], s)) return {k: k[i], s: s}
        }
        return null
    }
    // what of the panels is under p: {t: "tab" | "body", k, s}, or null
    function uiAt(p) {
        var t = tabAt(p)
        if (t) return {t: "tab", k: t.k, s: t.s}
        var l = openKind("left"), r = openKind("right")
        if (l !== "" && p.x < panelPx) return {t: "body", k: l, s: "left"}
        if (r !== "" && p.x >= view.width - panelPx) return {t: "body", k: r, s: "right"}
        return null
    }
    // a tab: opens its panel and folds every other kind, or folds its own
    function toggle(k, s) {
        var on = !kindOpen(k, s)
        if (on) {
            if (k !== "keys") { panelOpen = false; panelOpenR = false }
            if (k !== "mask") stripOpen = false
            if (k !== "trace") tstripOpen = false
        }
        if (k === "keys") { if (s === "right") panelOpenR = on; else panelOpen = on }
        else if (k === "mask") stripOpen = on
        else tstripOpen = on
        if (!on && kindShow(k) === "hover") setPeek(s, true)   // just folded under the pen: the tabs stay a moment
        act(k === "keys" ? "panel " + s + " " + (on ? 1 : 0) : (k === "mask" ? "maskstrip " : "tracestrip ") + (on ? 1 : 0))
    }
    function setPeek(s, on) {
        if (peeked(s) === on) return
        if (s === "right") peekR = on; else peekL = on
        act("peek " + (peekL ? 1 : 0) + " " + (peekR ? 1 : 0))
        if (!on) refreshScreen()   // the ink and paper under it come back in one clean pass
    }
    function unpeek() { hoverSide = ""; hoverTimer.stop(); setPeek("left", false); setPeek("right", false) }
    // the side under p whose panels are all folded and have a hidden tab ("left", "right" or ""):
    // hovering along that edge shows it
    function foldedEdgeAt(p) {
        var sides = ["left", "right"]
        for (var j = 0; j < 2; j++) {
            var s = sides[j], k = kinds(s), hid = false
            if (openKind(s) !== "") continue
            for (var i = 0; i < k.length; i++) if (kindShow(k[i]) === "hover") hid = true
            if (hid && (s === "right" ? p.x >= view.width - panelPx : p.x < panelPx)) return s
        }
        return ""
    }
    // hovering still for a moment brings the tabs up; contact never does, so a stroke can run
    // into the corner. They go a moment after the pen leaves that edge.
    function peekPen(p, touching, inRange) {
        var z = foldedEdgeAt(p)
        if (inRange && !touching && !penDown && z !== "" && !peeked(z)) {
            if (hoverSide !== z) { hoverSide = z; hoverTimer.restart() }
        } else if (hoverSide !== "") { hoverSide = ""; hoverTimer.stop() }
        if (!(peekL || peekR)) return
        if (inRange && (z !== "" && peeked(z) || penBtn === -2 || penBtn === -6 || stripPen)) peekHide.stop()
        else if (!peekHide.running) peekHide.restart()
    }
    readonly property bool anyHover: panelShow === "hover" || maskShow === "hover" || traceShow === "hover"
    onAnyHoverChanged: unpeek()
    Timer { id: hoverTimer; interval: 350; onTriggered: if (win.hoverSide !== "") { win.setPeek(win.hoverSide, true); win.hoverSide = "" } }
    Timer { id: peekHide; interval: 1200; onTriggered: win.unpeek() }
    // the panel with the gestures button and the light bar: the left one, else the right
    readonly property string mainSide: panelOnL ? "left" : panelOnR ? "right" : ""
    function sideOpen(s) { return s === "right" ? panelOpenR : panelOpen }
    function sideX(s) { return s === "right" ? view.width - panelPx : 0 }
    // the side whose shortcut panel (or its tab) is under p: "left", "right" or ""
    function panelAt(p) {
        var u = uiAt(p)
        return u && u.k === "keys" ? u.s : ""
    }
    readonly property real headH: 190   // buttons 32 px under the profile row, as far as the gestures button is under them
    readonly property real profY: tabS + 10   // the profile row: arrows either side of its name
    readonly property real profH: 72
    property string profileName: ""
    // "Finger gestures" at the foot of the panel opens a sheet listing them, as the PC sends
    // them ("gesturelist [[gesture, action], ...]"); a tap anywhere closes it
    property var gestureList: []
    property bool gestureSheet: false
    property bool sheetPen: false        // the pen closed the sheet: no ink until it lifts
    readonly property real gBtnY: view.height - footH + 24
    readonly property real gBtnH: 72
    function gestureBtnHit(p) {
        var s = panelAt(p)
        return s !== "" && s === mainSide && sideOpen(s) && gesturesOn && p.y >= gBtnY && p.y < gBtnY + gBtnH
    }
    onGestureSheetChanged: refreshScreen()
    // paper under the ink: plain | lined | squared | dots | cross | blueprint | isometric
    property string paper: "plain"
    property real paperStep: 45          // px between lines (the PC converts from mm)
    // tracing image under the ink: file on the tablet, its scale and offset in view pixels
    property string traceSrc: ""
    property real traceScale: 1
    property real traceX: 0
    property real traceY: 0
    property real traceOpacity: 0.5
    property bool traceAdjust: false     // fingers move / zoom the image instead of gestures
    property int lightPct: -1            // front light in percent; -1: unknown or no front light (bar hidden)
    readonly property bool lightOn: lightPct >= 100
    readonly property bool lightBar: lightPct >= 0
    property bool nativeTouch: false     // fingers go to Windows as real touch, no gestures here
    // pen mask: the PC keeps it and sends it as an image (black, alpha = how masked); it is made
    // and placed in the desktop app, and only switched and inverted here
    property string maskSrc: ""
    // the mask panel: the PC's masks, two across; a tap picks one
    property bool stripAvail: false      // there are masks: its corner tab shows, the panel opens from it
    property bool stripOpen: false
    property string stripSide: "right"
    property var maskList: []            // [{id, name, thumb}]
    property string maskActive: ""
    // the tracing image panel: the same for the PC's tracing images
    property bool tstripAvail: false
    property bool tstripOpen: false
    property string tstripSide: "right"
    property var traceList: []           // [{id, name, thumb}]
    property string traceActive: ""
    property bool stripPen: false        // the pen went down in one of them: nothing else until it lifts
    // what the open panel on each side keeps from the drawing area: nothing with "tap", the pen draws there
    function resOf(s) { var k = openKind(s); return k !== "" && kindShow(k) !== "tap" ? panelPx : 0 }
    readonly property real resL: resOf("left")
    readonly property real resR: resOf("right")
    readonly property real tileW: narrow ? panelPx - 24 : (panelPx - 36) / 2
    readonly property real stripThumbH: tileW * view.height / view.width
    readonly property real stripTileH: stripThumbH + 46
    readonly property int stripTop: narrow ? 260 : 180   // the thumbnails start under the two buttons (stacked when narrow)
    // narrow: the height the tiles scroll in
    function listH(k) { return (k === "mask" ? paperTileY - 10 : view.height - 10) - stripTop }
    // a touch in the open mask / tracing image panel on side s: its two buttons, a thumbnail, the paper
    function listPick(k, s, p) {
        var lx = p.x - sideX(s), second = narrow ? p.y >= 176 && p.y < 246 : lx >= panelPx / 2
        if (narrow ? p.y >= 96 && p.y < 246 : p.y >= 96 && p.y < 166) {
            if (narrow && p.y >= 166 && p.y < 176) return   // the gap between the two
            if (second) pickId(k, "none")
            else if (k === "mask") act("maskinvert")   // the panel stays open to show it
            else if (traceActive !== "") { tstripOpen = false; act("tracestrip 0"); act("traceadjust") }   // Move: out of the way
            return
        }
        if (k === "mask" && p.y >= paperTileY && p.y < paperTileY + paperTileH) {  // the paper: left half back, right half on
            if (narrow) second = lx >= panelPx / 2
            var c = papers.indexOf(paper), n = papers.length
            act("paper " + papers[((c < 0 ? 0 : c) + (second ? 1 : n - 1)) % n])
            return
        }
        if (p.y < stripTop) return
        var list = k === "mask" ? maskList : traceList, pitch = stripTileH + 10
        if (narrow) {
            if (p.y >= stripTop + listH(k)) return
            var j = Math.floor((p.y - stripTop + scrollOf(k)) / pitch)
            if (j >= 0 && j < list.length && (p.y - stripTop + scrollOf(k)) - j * pitch < stripTileH) pickId(k, list[j].id)
            return
        }
        var row = Math.floor((p.y - stripTop) / pitch), i = row * 2 + (second ? 1 : 0)
        if (i < list.length && (p.y - stripTop) - row * pitch < stripTileH && tileFits(k, row)) pickId(k, list[i].id)
    }
    function tileFits(k, row) {
        return stripTop + row * (stripTileH + 10) + stripTileH <= (k === "mask" ? paperTileY - 10 : view.height - 10)
    }
    function pickId(k, id) {  // picked: the panel folds away
        if (k === "mask") { stripOpen = false; act("maskpick " + id) }
        else { tstripOpen = false; act("tracepick " + id) }
        if (kindShow(k) === "hover") setPeek(k === "mask" ? stripSide : tstripSide, true)
    }
    function stripTouch(u, p) { if (u.t === "tab") toggle(u.k, u.s); else listPick(u.k, u.s, p) }
    // the paper selector at the foot of the strip, in the PC's order (core.PAPERS)
    readonly property var papers: ["plain", "lined", "squared", "dots", "cross", "blueprint", "isometric"]
    readonly property var paperNames: ({ plain: "Plain", lined: "Lined", squared: "Squared", dots: "Dots",
                                         cross: "Crosses", blueprint: "Blueprint", isometric: "Isometric" })
    readonly property real paperTileH: 110
    readonly property real paperTileY: view.height - 24 - paperTileH
    property bool maskOn: false
    property bool maskInvert: false
    property int profileCount: 1
    // E-paper update mode of the ink area (main.cpp hands over its EPScreenModeItem and the mode
    // numbers). Pen mode only flushes on pen activity, so other changes to what is under the ink
    // (paper, tracing image, mask, area) get a short switch to Content mode to reach the panel.
    property var penModeItem: null
    property int modePen: -1
    property int modeUI: -1
    property int modeAnim: -1
    property int modeContent: -1
    property bool epRefreshing: false
    function epMode() {
        if (!penModeItem) return
        // fingers moving the image: the fast animation mode, one clean pass when they lift
        var m = penDown ? modePen : adj ? (modeAnim >= 0 ? modeAnim : modeUI) : epRefreshing ? modeContent : modePen
        if (m >= 0 && penModeItem.mode !== m) penModeItem.mode = m
    }
    function refreshScreen() { epDebounce.restart() }
    onPaperChanged: refreshScreen()
    onPaperStepChanged: refreshScreen()
    onTraceSrcChanged: refreshScreen()
    onTraceOpacityChanged: refreshScreen()
    onTraceScaleChanged: refreshScreen()
    onTraceXChanged: refreshScreen()
    onTraceYChanged: refreshScreen()
    onTraceAdjustChanged: refreshScreen()
    property bool imgMoved: false
    onAdjChanged: { if (!adj && imgMoved) { imgMoved = false; fullRefresh() } else epMode() }
    onMaskOnChanged: refreshScreen()
    onMaskInvertChanged: refreshScreen()
    onMaskActiveChanged: refreshScreen()
    onStripAvailChanged: refreshScreen()
    onMaskSrcChanged: refreshScreen()
    onMaskListChanged: refreshScreen()
    onResLChanged: refreshScreen()
    onResRChanged: refreshScreen()
    onStripOpenChanged: refreshScreen()
    onTstripOpenChanged: refreshScreen()
    onTstripAvailChanged: refreshScreen()
    onTraceListChanged: refreshScreen()
    onTraceActiveChanged: refreshScreen()
    onAreaChanged: refreshScreen()
    onModeChanged: refreshScreen()
    onPenDownChanged: epMode()
    readonly property real footH: lightBar ? 240 : 120
    // the light bar at the foot of the panel: tap or drag along it, left end = off
    readonly property real lightY: view.height - 92
    readonly property real lightH: 66
    function lightHit(p) {
        var s = panelAt(p)
        return lightBar && s !== "" && s === mainSide && sideOpen(s) && p.y >= lightY - 40 && p.y < lightY + lightH + 20
    }
    function lightAt(p) {
        var f = (p.x - sideX(mainSide) - 16) / Math.max(1, panelPx - 32)
        var pct = Math.max(0, Math.min(10, Math.round(f * 10))) * 10
        if (pct === lightPct) return
        lightPct = pct
        console.warn("LIGHT:" + pct)   // main.cpp sets the light itself and tells the PC
    }
    readonly property int rows: 8
    readonly property real cellW: panelPx / cols
    readonly property real btnAreaH: view.height - headH - footH
    // narrow: the panel without the gestures button and light bar runs its buttons to the bottom
    function footOf(s) { return narrow && s !== mainSide ? 8 : footH }
    function areaOf(s) { return view.height - headH - footOf(s) }
    // narrow: whole rows of about 120 px show, the rest scroll
    readonly property int rowsShown: narrow ? Math.max(1, Math.floor(btnAreaH / 120)) : rows
    readonly property real cellH: btnAreaH / rowsShown
    // ---- narrow panels scroll: by panel ("left" / "right" shortcuts, "mask", "trace")
    function scrollOf(key) { return narrow ? (scrolls[key] || 0) : 0 }
    function scrollMax(key) {
        if (key === "mask" || key === "trace") {
            var n = (key === "mask" ? maskList : traceList).length
            return Math.max(0, n * (stripTileH + 10) - listH(key))
        }
        var first = key === "right" ? 16 : 0
        var nb = Math.max(0, Math.min(16, buttons.length - first))
        return Math.max(0, nb * cellH - areaOf(key))
    }
    function setScroll(key, v) {
        var o = {}
        for (var k in scrolls) o[k] = scrolls[k]
        o[key] = Math.max(0, Math.min(scrollMax(key), v))
        if (o[key] === scrolls[key]) return
        scrolls = o
    }
    onScrollsChanged: refreshScreen()
    onButtonsChanged: { setScroll("left", scrollOf("left")); setScroll("right", scrollOf("right")) }
    // the scrolling part of the panel under p: its key, or "" (narrow only)
    function scrollKeyAt(p) {
        if (!narrow) return ""
        var u = uiAt(p)
        if (!u || u.t !== "body") return ""
        if (u.k === "keys") return sideOpen(u.s) && p.y >= headH && p.y < view.height - footOf(u.s) ? u.s : ""
        return p.y >= stripTop && p.y < stripTop + listH(u.k) ? u.k : ""
    }

    // The PC sends its own layout ("buttons [json]"); this is the same as its default.
    // kind: tap (keys), hold (keys held / locked), pen, snap, local (clear ink), none
    property var buttons: [
        {t: "Undo", s: "Ctrl Z", kind: "tap"},         {t: "Redo", s: "Ctrl Shift Z", kind: "tap"},
        {t: "Size -", s: "[", kind: "tap"},            {t: "Size +", s: "]", kind: "tap"},
        {t: "Brush", s: "B", kind: "tap"},             {t: "Eraser", s: "E", kind: "tap"},
        {t: "Hand", s: "holds Space", kind: "hold"},   {t: "Pick", s: "holds Alt", kind: "hold"},
        {t: "Ctrl", s: "holds Ctrl", kind: "hold"},    {t: "Shift", s: "holds Shift", kind: "hold"},
        {t: "Zoom -", s: "Ctrl -", kind: "tap"},       {t: "Zoom +", s: "Ctrl =", kind: "tap"},
        {t: "Fit", s: "Ctrl 0", kind: "tap"},          {t: "Shapes", s: "", kind: "snap"},
        {t: "Pen", s: "", kind: "pen"},                {t: "Save", s: "Ctrl S", kind: "tap"}
    ]

    // To the PC: one line on stderr, picked out by the C++ message handler.
    function act(s) { console.warn("ACT:" + s) }
    function say(s) { toast = s; toastTimer.restart() }

    function command(line) {
        if (line.indexOf("buttons ") === 0) {
            try { buttons = JSON.parse(line.substring(8)); latched = ({}) }
            catch (e) { console.warn("LOG:bad buttons line: " + e) }
            return
        }
        var a = line.split(" ")
        var c = a.shift()
        if (c === "rot") rot = parseInt(a[0]) % 4
        else if (c === "mode") { mode = a[0]; endStroke(); if (mode !== "ink") { clearInk(); gestureSheet = false } }
        else if (c === "next") nextTarget = parseInt(a[0])
        else if (c === "status") status = a.join(" ")
        else if (c === "area") area = a.map(parseFloat)
        else if (c === "fade") fadeMs = Math.max(0, parseInt(a[0]))
        else if (c === "clear") clearInk()
        else if (c === "snap") snap(a)
        else if (c === "panel") { panelSide = a[0]; if (a.length > 1) panelFrac = parseFloat(a[1]) }
        else if (c === "cols") { cols = parseInt(a[0]) === 1 ? 1 : 2 }
        else if (c === "panelshow") { panelShow = a[0]; maskShow = a[1] || "always"; traceShow = a[2] || "always"; unpeek() }
        else if (c === "panelopen") { panelOpen = a[0] === "1"; if (a.length > 1) panelOpenR = a[1] === "1" }
        else if (c === "paper") { paper = a[0]; if (a.length > 1) paperStep = Math.max(12, parseFloat(a[1])) }
        else if (c === "trace") {  // trace <opacity> <scale> <x> <y> <file or empty>
            traceOpacity = parseFloat(a[0]); traceScale = parseFloat(a[1])
            traceX = parseFloat(a[2]); traceY = parseFloat(a[3])
            var src = a.slice(4).join(" ")
            traceSrc = src ? "file://" + src : ""
        }
        else if (c === "traceadjust") traceAdjust = a[0] === "1"
        else if (c === "mask") {  // mask <on> <inverted>
            maskOn = a[0] === "1"; maskInvert = a[1] === "1"
        }
        else if (c === "maskimg") { maskSrc = ""; if (a.length && a[0]) maskSrc = "file://" + a.join(" ") }
        else if (c === "maskstrip") {  // maskstrip <there> <side> <width frac> <open>
            stripAvail = a[0] === "1"; stripSide = a[1] || "right"; stripOpen = a[3] === "1"
        }
        else if (c === "tracestrip") {  // tracestrip <there> <side> <open>
            tstripAvail = a[0] === "1"; tstripSide = a[1] || "right"; tstripOpen = a[2] === "1"
        }
        else if (c === "traces") { var tl = JSON.parse(a.join(" ")); traceActive = tl.active; traceList = tl.list }
        else if (c === "masks") { var m = JSON.parse(a.join(" ")); maskActive = m.active; maskList = m.list }
        else if (c === "profile") { profileCount = parseInt(a[1]); profileName = a.slice(2).join(" ") }
        else if (c === "gestures") {
            gesturesOn = a[0] === "1"
            if (a.length > 1) swipeStep = parseFloat(a[1])
            if (a.length > 2) palmSize = parseFloat(a[2])
            if (a.length > 3) nativeTouch = a[3] === "1"
        }
        else if (c === "toast") say(a.join(" "))
        else if (c === "gesturelist") { try { gestureList = JSON.parse(a.join(" ")) } catch (e) { gestureList = [] } }
        else if (c === "state") {
            for (var i = 0; i + 1 < a.length; i += 2) {
                if (a[i] === "pen") penOut = a[i + 1] === "1"
                else if (a[i] === "snap") snapOn = a[i + 1] === "1"
            }
        } else if (c === "light") lightPct = parseInt(a[0])
        else if (c === "unlatch") latched = ({})
    }

    function clearInk() {
        stroke = null; last = null; lastStroke = null; held = null
        // only strokes: the e-paper pen-mode item also lives in `ink` and must stay
        for (var i = ink.children.length - 1; i >= 0; i--)
            if (ink.children[i].trail) ink.children[i].destroy()
    }

    // "snap W x y x y ...": the PC recognised a shape. Replace the stroke with the clean outline
    // (points as fractions of the digitizer, like the pen) and ignore the pen until it lifts.
    function snap(a) {
        var victim = stroke || lastStroke
        if (victim) victim.destroy()
        stroke = null; last = null; lastStroke = null
        if (mode !== "ink") return
        var w = 2 + 5 * parseFloat(a[0])
        var st = fader.createObject(ink, {})
        var prev = null
        for (var i = 1; i + 1 < a.length; i += 2) {
            var p = view.mapFromItem(win.contentItem, parseFloat(a[i]) * win.width, parseFloat(a[i + 1]) * win.height)
            if (prev) {
                var dx = p.x - prev.x, dy = p.y - prev.y
                seg.createObject(st, {x: prev.x, y: prev.y, len: Math.sqrt(dx * dx + dy * dy), w: w,
                                      rotation: Math.atan2(dy, dx) * 180 / Math.PI})
            }
            prev = p
        }
        if (penDown) held = st
        else if (fadeMs > 0) st.fade(fadeMs)
    }

    function hintHit(item, p) {
        if (!item.visible) return false
        var q = item.mapFromItem(view, p.x, p.y)
        return q.x >= -20 && q.y >= -20 && q.x < item.width + 20 && q.y < item.height + 20
    }
    // ---- panel: the fold tab and the buttons, by finger or pen
    function tabHit(p) {  // the side whose shortcut panel's tab is under p, or ""
        var t = tabAt(p)
        return t && t.k === "keys" ? t.s : ""
    }
    function inPanel(p) { return uiAt(p) !== null }

    // -1 / +1 on the profile arrows (only with more than one profile), 0 elsewhere
    function profileArrow(p) {
        var s = panelAt(p)
        if (s === "" || !sideOpen(s) || profileCount < 2 || p.y < profY || p.y >= profY + profH) return 0
        var x = p.x - sideX(s)
        return x < panelPx * 0.3 ? -1 : x >= panelPx * 0.7 ? 1 : 0
    }
    function buttonAt(p) {
        var s = panelAt(p)
        if (s === "" || !sideOpen(s) || p.y < headH || p.y >= view.height - footOf(s)) return -1
        var i = narrow ? Math.floor((p.y - headH + scrollOf(s)) / cellH) + (s === "right" ? 16 : 0)
                       : Math.floor((p.y - headH) / cellH) * 2 + (p.x - sideX(s) >= cellW ? 1 : 0) + (s === "right" ? 16 : 0)
        if (narrow && (i - (s === "right" ? 16 : 0)) >= 16) return -1
        return i < buttons.length ? i : -1
    }
    function setLatch(i, on) {
        var l = {}
        for (var key in latched) if (latched[key]) l[key] = true
        if (on) l[i] = true; else delete l[i]
        latched = l
    }
    function fold(s) { toggle("keys", s) }
    // Returns what was pressed: -2 for the fold tab, a button index, or -1.
    function pressAt(p) {
        var t = tabHit(p)
        if (t !== "") { fold(t); return t === "right" ? -6 : -2 }
        if (gestureBtnHit(p)) { gestureSheet = !gestureSheet; return -4 }
        if (lightHit(p)) { lightAt(p); return -5 }
        var arrow = profileArrow(p)
        if (arrow) { latched = ({}); act("profile " + (arrow > 0 ? "next" : "prev")); return -3 }
        var i = buttonAt(p)
        pressBtn(i)
        return i
    }
    function pressBtn(i) {
        if (i < 0) return
        var b = buttons[i]
        if (!b || b.kind === "none") return
        pressing = i
        if (b.kind === "tap") { act("press " + i); say(b.t) }
        else if (b.kind === "pen") { penOut = !penOut; act("pen " + (penOut ? 1 : 0)); say(penOut ? "Pen on" : "Pen off") }
        else if (b.kind === "snap") { snapOn = !snapOn; act("snap " + (snapOn ? 1 : 0)); say(snapOn ? "Shapes on" : "Shapes off") }
        else if (b.kind === "local") { clearInk() }
        else if (b.kind === "trace") { act("traceadjust") }
        else if (b.kind === "light") { act("light") }
        else if (b.kind === "mask") { act("maskinvert") }
        else if (b.kind === "hold") {
            if (latched[i]) { act("release " + i); setLatch(i, false); keepLatch = false; say(b.t + " released") }
            else { act("press " + i); setLatch(i, true); keepLatch = true; holdStart = Date.now() }
        }
    }
    // A quick tap locks a hold button down until it's tapped again; holding it with a finger
    // works like the key itself (down while touched). The pen always locks.
    function releaseBtn(i, byPen) {
        pressing = -1
        if (i < 0) return
        var b = buttons[i]
        if (!b || b.kind !== "hold" || !keepLatch) return
        keepLatch = false
        if (!byPen && Date.now() - holdStart > 400) { act("release " + i); setLatch(i, false) }
        else say(b.t + " locked: tap again to release")
    }

    // Each segment is its own small item rather than pixels in one big Canvas: a Canvas
    // re-uploads the whole 1620x2160 texture per change, so the e-paper backend refreshes a
    // large area every time. Small items keep each update to the few pixels the pen touched.
    function pen(px, py, pressure, touching, eraser, inRange) {
        if (inRange) {
            penSeen = Date.now()
            if (gMode !== "" && gMode !== "dead") { endGesture(); sendTouch() }  // the pen came back: a hand on the screen is a palm
        }
        var p = view.mapFromItem(win.contentItem, px, py)
        if (anyHover && mode === "ink") peekPen(p, touching, inRange)
        var u = uiAt(p), mine = u !== null && kindShow(u.k) !== "tap"   // "tap": the pen draws through
        if (stripPen || (touching && mine && u.k !== "keys")) {  // the mask and tracing image panels take the pen (so does the PC)
            endStroke()
            if (touching && !stripPen) { stripPen = true; stripTouch(u, p) }
            if (!touching) stripPen = false
            return
        }
        if (penBtn !== -1 || (touching && mine)) {
            // the shortcut panel takes the pen; the PC ignores the pen over the panel too
            endStroke()
            if (touching && penBtn === -1) { penBtn = pressAt(p); if (penBtn === -1) penBtn = 99 }
            else if (touching && penBtn === -5 && lightHit(p)) lightAt(p)   // dragging along the light bar
            else if (!touching || !inPanel(p)) { if (penBtn >= 0 && penBtn !== 99) releaseBtn(penBtn, true); else pressing = -1; penBtn = -1 }
            return
        }
        if (sheetPen || (touching && gestureSheet)) {  // a tap closes the gestures sheet, and draws nothing
            endStroke()
            if (touching && !sheetPen) { gestureSheet = false; sheetPen = true }
            if (!touching) sheetPen = false
            return
        }
        penDown = touching
        if (held) {
            if (touching) return
            if (fadeMs > 0) held.fade(fadeMs)
            held = null
        }
        if (mode !== "ink" || !touching || eraser) { endStroke(); return }
        if (!stroke) { stroke = fader.createObject(ink, {}); last = p; return }
        var dx = p.x - last.x, dy = p.y - last.y
        var len = Math.sqrt(dx * dx + dy * dy)
        if (len < 2) return
        seg.createObject(stroke, {x: last.x, y: last.y, len: len, w: 2 + 5 * pressure,
                                  rotation: Math.atan2(dy, dx) * 180 / Math.PI})
        last = p
    }

    function endStroke() {
        if (stroke && fadeMs > 0) stroke.fade(fadeMs)
        if (stroke) lastStroke = stroke
        stroke = null; last = null
    }

    // ---- finger gestures on the drawing area
    //   two fingers: drag = pan (the PC holds Space and drags), pinch = zoom in / out
    //   three fingers: swipe right-to-left = undo, left-to-right = redo
    //   five fingers: twist = rotate the canvas (the PC holds the rotate key and drags in a circle)
    // Ignored while the pen is near the screen (that's a resting hand) and with 6+ fingers.
    property var gPts: ({})        // pointId -> {x, y}
    property string gMode: ""      // "" | pan | pinch | three | five | rotate | dead
    property var gAng0: ({})       // five fingers: pointId -> angle around the centroid at the start
    property real gRotSent: 0      // degrees last sent
    property int gMax: 0
    property real gD0: 0           // finger distance when the second finger landed
    property real gDLast: 0        // distance at the last zoom step
    property var gC0: null         // centroid when the current finger count began
    property var gSent: null       // last pan offset sent
    property var touchBtn: ({})    // pointId -> panel item, for fingers that landed on the panel
    // narrow panels: pointId -> {key, y0, s0, p, moved, pressed, btn} for a finger on a scrolling
    // part (touchBtn -7). A drag scrolls; a tap presses on lifting; holding still presses (hold keys)
    property var drags: ({})
    Timer {
        id: dragHold; interval: 350
        onTriggered: {
            var d = win.drags
            for (var k in d) {
                var g = d[k]
                if (g.moved || g.pressed || g.key === "mask" || g.key === "trace") continue
                g.pressed = true; g.btn = win.pressAt(g.p)
            }
            win.drags = d
        }
    }
    property real palmSize: 0      // contact size (panel units) above which a touch is a palm; 0 = off
    property var palms: ({})       // pointId -> true: contacts judged to be a palm, ignored until lifted
    property real gLastEv: 0       // last touch event of any kind, for the stuck-contact sweep
    property real swipeStep: 100   // three-finger swipe: px of drag per undo / redo step
    property int gSteps: 0         // net steps sent this swipe: < 0 undos, > 0 redos
    // taps: a touch (all fingers down and up again) that is short and barely moves
    property var gStart: ({})      // pointId -> where it landed
    property real gMoved: 0        // furthest any finger strayed this touch
    property real gT0: 0           // when the first finger landed
    property bool gTapOk: true     // nothing (pan, zoom, swipe, pen) happened this touch
    property int tapN: 0           // fingers of the tap series in progress
    property int tapK: 0           // taps so far in it

    function gList() { var l = []; for (var k in gPts) l.push(gPts[k]); return l }
    function centroid(l) {
        var x = 0, y = 0
        for (var i = 0; i < l.length; i++) { x += l[i].x; y += l[i].y }
        return {x: x / l.length, y: y / l.length}
    }
    function spread(l) { return Math.sqrt(Math.pow(l[0].x - l[1].x, 2) + Math.pow(l[0].y - l[1].y, 2)) }
    function fingerAngles(l, ids) {
        var c = centroid(l), out = {}
        for (var i = 0; i < ids.length; i++) { var p = gPts[ids[i]]; out[ids[i]] = Math.atan2(p.y - c.y, p.x - c.x) }
        return out
    }
    function twist() {  // mean turn of the five fingers since the start, in degrees (clockwise +)
        var ids = Object.keys(gPts), now = fingerAngles(gList(), ids), sum = 0, n = 0
        for (var i = 0; i < ids.length; i++) {
            if (!(ids[i] in gAng0)) continue
            var d = now[ids[i]] - gAng0[ids[i]]
            while (d > Math.PI) d -= 2 * Math.PI
            while (d < -Math.PI) d += 2 * Math.PI
            sum += d; n++
        }
        return n ? sum / n * 180 / Math.PI : 0
    }
    function endGesture() {
        if (gMode === "pan") act("pan end")
        if (gMode === "rotate") act("rotate end")
        gMode = "dead"   // until every finger is up
        gTapOk = false
    }
    // A finished touch: count it towards a tap series and report the series once no further
    // tap follows (the PC decides what "tap 1 3" etc. do; unassigned ones do nothing).
    function touchEnded() {
        // five fingers never land or lift quite together, so they get a little longer
        var tap = gTapOk && (gMax <= 3 || gMax === 5) && gMoved < 30 && Date.now() - gT0 < (gMax === 5 ? 500 : 350)
        if (!tap) { tapTimer.stop(); tapK = 0; return }
        if (tapTimer.running && tapN === gMax) tapK++
        else { tapN = gMax; tapK = 1 }
        tapTimer.restart()
    }
    // Contact size as Qt reports it (the panel's ABS_MT_TOUCH_MAJOR); 0 if the platform gives none.
    function touchSize(t) {
        var d = t.ellipseDiameters
        return d ? Math.max(d.width, d.height) : 0
    }
    // A palm: drop the contact and end whatever gesture it was part of. Sticky until it lifts,
    // because a palm often lands small at its edge and grows.
    function palmCheck(t) {
        if (palmSize <= 0 || touchSize(t) <= palmSize || palms[t.pointId]) return false
        var pl = palms; pl[t.pointId] = true; palms = pl
        console.warn("LOG:palm " + Math.round(touchSize(t)))
        if (t.pointId in gPts) { var g = gPts; delete g[t.pointId]; gPts = g }
        endGesture()
        return true
    }
    // A contact whose release got lost would block gestures for good: after 3 s with no touch
    // events at all, forget every contact.
    Timer {
        interval: 1000; repeat: true; running: Object.keys(win.gPts).length > 0
        onTriggered: if (Date.now() - win.gLastEv > 3000) {
            console.warn("LOG:touch sweep " + Object.keys(win.gPts).length)
            win.endGesture(); win.gPts = ({}); win.palms = ({}); win.fingersChanged(); win.sendTouch()
        }
    }
    Timer {  // changes settle, then one Content-mode pass (not while the pen is drawing)
        id: epDebounce; interval: 250
        onTriggered: {
            if (!win.penModeItem) return
            if (win.penDown || win.adj) { restart(); return }
            win.epRefreshing = true; win.epMode(); epNudge.flip = !epNudge.flip; win.requestUpdate(); epBack.restart()
        }
    }
    Timer { id: epBack; interval: 1500; onTriggered: { win.epRefreshing = false; win.epMode() } }
    // Whole-screen clean refresh (five fingers swiped down): black for a moment, then the page,
    // both in Content mode, which clears e-ink leftovers.
    function fullRefresh() {
        epDebounce.stop(); epRefreshing = true; epMode()
        epCover.visible = true; win.requestUpdate(); epUncover.restart()
    }
    Timer {
        id: epUncover; interval: 350
        onTriggered: { epCover.visible = false; epNudge.flip = !epNudge.flip; win.requestUpdate(); epBack.restart() }
    }
    Timer { id: tapTimer; interval: 330; onTriggered: { if (win.tapK > 0) win.act("tap " + win.tapN + " " + win.tapK); win.tapK = 0 } }
    // Adjusting the tracing image: one finger drags it, two zoom it (about its centre).
    property var adj: null         // {c, d, x, y, s} where the current finger count began
    function adjustChanged() {
        var l = gList(), n = l.length
        if (n === 0) {
            if (adj && adj.tap && adj.moved < 20 && hintHit(traceHint, adj.c)) {
                traceX = adj.x; traceY = adj.y; traceScale = adj.s
                act("traceadjust")  // "tap here when done"
            } else if (adj) act("trace " + traceX.toFixed(1) + " " + traceY.toFixed(1) + " " + traceScale.toFixed(4))
            adj = null; gMode = ""; gMax = 0; return
        }
        var first = !adj
        adj = {c: centroid(l), d: n > 1 ? spread(l) : 0, x: traceX, y: traceY, s: traceScale,
               tap: first ? n === 1 : false, moved: 0}
    }
    function adjustMoved() {
        var l = gList()
        if (!adj || !l.length) return
        var c = centroid(l)
        adj.moved = Math.max(adj.moved, Math.abs(c.x - adj.c.x) + Math.abs(c.y - adj.c.y))
        if (adj.moved > 5) imgMoved = true
        traceX = adj.x + c.x - adj.c.x
        traceY = adj.y + c.y - adj.c.y
        if (l.length > 1 && adj.d > 20) traceScale = Math.max(0.05, Math.min(20, adj.s * spread(l) / adj.d))
    }
    // Every contact to the PC as fractions of the view: "touch live|dead <palms> id x y ...". The PC
    // shows them on its live view and, in Windows-touch mode, injects them ("dead" = lift them all).
    function sendTouch() {
        var out = ["touch", gMode === "dead" || traceAdjust ? "dead" : "live", Object.keys(palms).length]
        for (var id in gPts)
            out.push(id, (gPts[id].x / view.width).toFixed(4), (gPts[id].y / view.height).toFixed(4))
        var line = out.join(" ")
        if (line === lastTouch) return  // a resting finger repeats itself many times a second
        lastTouch = line
        act(line)
    }
    property string lastTouch: ""
    function fingersChanged() {
        if (traceAdjust) { adjustChanged(); return }
        var l = gList(), n = l.length
        gMax = Math.max(gMax, n)
        if (n === 0) {
            if (gMode === "pan") act("pan end")
            if (gMode === "rotate") act("rotate end")
            if (gMax > 0 && !nativeTouch) touchEnded()
            gMode = ""; gMax = 0; gC0 = null; gMoved = 0; gTapOk = true; gStart = ({}); gT0 = 0; return
        }
        if (gT0 === 0) gT0 = Date.now()
        if (gMode === "dead") return
        if (gMax > 5 || Date.now() - penSeen < 700 || !gesturesOn || mode !== "ink") { endGesture(); return }
        if (nativeTouch) { gMode = "native"; return }
        if (gMode === "rotate" && n !== 5) { endGesture(); return }
        if (n === 5) {
            if (gMode === "three" && gSteps !== 0) { endGesture(); return }
            if (gMode === "pan") act("pan end")
            gMode = "five"; gC0 = centroid(l); gAng0 = fingerAngles(l, Object.keys(gPts)); gRotSent = 0
        } else if (gMode === "five") {
            gMode = "dead"   // a finger lifted before any turn: just a five-finger touch
        } else if (n === 3) {
            if (gMode === "pan") act("pan end")
            gMode = "three"; gC0 = centroid(l); gSteps = 0
        } else if (n === 2 && gMode === "") {
            gC0 = centroid(l); gD0 = spread(l); gDLast = gD0
        } else if (n < 2 && (gMode === "pan" || gMode === "pinch")) {
            endGesture()
        }
    }
    function fingersMoved() {
        if (traceAdjust) { adjustMoved(); return }
        var l = gList()
        for (var id in gPts) {
            var a = gPts[id], b = gStart[id]
            if (b) gMoved = Math.max(gMoved, Math.abs(a.x - b.x) + Math.abs(a.y - b.y))
        }
        if (nativeTouch) return
        if (gMode === "dead" || !gC0) return
        if (l.length === 2 && (gMode === "" || gMode === "pan" || gMode === "pinch")) {
            var c = centroid(l), d = spread(l)
            if (gMode === "") {
                if (gD0 > 0 && Math.abs(d / gD0 - 1) > 0.18) { gMode = "pinch"; gDLast = gD0 }
                else if (Math.abs(c.x - gC0.x) + Math.abs(c.y - gC0.y) > 30) { gMode = "pan"; act("pan begin"); gSent = {x: 0, y: 0} }
            }
            if (gMode !== "") gTapOk = false
            if (gMode === "pinch") {
                while (d / gDLast > 1.25) { act("zoomin"); gDLast *= 1.25; say("Zoom in") }
                while (d / gDLast < 0.8) { act("zoomout"); gDLast *= 0.8; say("Zoom out") }
            } else if (gMode === "pan") {
                var dx = c.x - gC0.x, dy = c.y - gC0.y
                if (Math.abs(dx - gSent.x) + Math.abs(dy - gSent.y) >= 3) {
                    act("pan " + Math.round(dx) + " " + Math.round(dy)); gSent = {x: dx, y: dy}
                }
            }
        } else if ((gMode === "five" || gMode === "rotate") && l.length === 5) {
            var a = twist()
            if (gMode === "five") {
                var c5 = centroid(l), dy5 = c5.y - gC0.y
                if (dy5 > 180 && Math.abs(c5.x - gC0.x) < dy5 * 0.6 && Math.abs(a) < 8) {
                    gMode = "dead"; gTapOk = false; clearInk(); fullRefresh(); say("Ink cleared"); act("inkcleared"); return
                }
                if (Math.abs(a) < 8) return
                gMode = "rotate"; gTapOk = false; act("rotate begin")
            }
            if (Math.abs(a - gRotSent) >= 1) { act("rotate " + a.toFixed(1)); gRotSent = a }
        } else if (gMode === "three" && l.length === 3) {
            // one undo per step of drag to the left, one redo per step to the right; dragging
            // back takes steps back. Mostly sideways only, so a vertical slide does nothing.
            var c3 = centroid(l), sx = c3.x - gC0.x, sy = c3.y - gC0.y
            if (gSteps === 0 && Math.abs(sx) < 1.5 * Math.abs(sy)) return
            var k = Math.floor(Math.abs(sx) / swipeStep), target = sx < 0 ? -k : k
            if (target === gSteps) return
            gTapOk = false
            while (gSteps > target) { act("undo"); gSteps-- }
            while (gSteps < target) { act("redo"); gSteps++ }
            say(gSteps < 0 ? "Undo " + (-gSteps) : gSteps > 0 ? "Redo " + gSteps : "No change")
        }
    }
    function fingersUp() {
        if (gMode === "three") { gMode = "dead"; if (gSteps !== 0) gTapOk = false }
    }

    Timer { id: toastTimer; interval: 1600; onTriggered: win.toast = "" }

    Component {  // one stroke, live or finished
        id: fader
        Item {
            id: st
            property bool trail: true
            function fade(ms) { hold.interval = ms; hold.start() }
            // E-ink can't fade smoothly (grey steps ghost and flash in the fast pen waveform),
            // so a trail holds for fadeMs after the pen lifts and is then removed in one update.
            Timer { id: hold; onTriggered: st.destroy() }
        }
    }

    Component {
        id: seg
        Item {  // zero-size pivot at the segment start; rotation turns it toward the end point
            property real len
            property real w
            Rectangle { x: -w / 2; y: -w / 2; width: len + w; height: w; radius: w / 2; color: "black"; antialiasing: false }
        }
    }

    Item {
        id: view
        width: rot % 2 ? win.height : win.width
        height: rot % 2 ? win.width : win.height
        anchors.centerIn: parent
        rotation: rot * 90

        // ------------------------------------------------ paper and tracing image, under the ink
        // Drawn once as plain black items: crisp 1-3 px lines stay sharp on e-ink, where
        // grey or anti-aliased strokes dither. Only the drawing area, never under the panel.
        Item {
            id: paperArea
            visible: win.mode === "ink"
            x: win.resL
            width: view.width - win.resL - win.resR; height: view.height
            clip: true
            Image {
                visible: win.traceSrc !== ""
                source: win.traceSrc
                asynchronous: true; cache: false; smooth: true
                sourceSize.width: 2400; sourceSize.height: 2400   // keep memory sane for huge photos
                fillMode: Image.PreserveAspectFit
                width: Math.max(1, view.width * win.traceScale); height: Math.max(1, view.height * win.traceScale)
                x: (paperArea.width - width) / 2 + win.traceX; y: (paperArea.height - height) / 2 + win.traceY
                opacity: win.traceOpacity
            }
            Loader {
                anchors.fill: parent
                active: win.paper !== "plain"
                sourceComponent: win.paper === "dots" || win.paper === "cross" ? marks : lines
            }
            Image {  // pen mask: shaded where the pen is held back
                visible: win.maskOn
                x: -paperArea.x; width: view.width; height: view.height
                source: win.maskSrc
                cache: false; smooth: true
                opacity: 0.4
            }
            Rectangle {  // while adjusting: a frame says fingers move the image
                visible: win.traceAdjust; anchors.fill: parent; anchors.margins: 6
                color: "transparent"; border.width: 6; border.color: "black"
                Rectangle {
                    id: traceHint
                    anchors.horizontalCenter: parent.horizontalCenter; y: 24; width: hint.width + 40; height: hint.height + 24
                    color: "black"; radius: 12
                    Text { id: hint; anchors.centerIn: parent; color: "white"; font.pixelSize: 26; font.bold: true
                           horizontalAlignment: Text.AlignHCenter
                           text: "Moving the image: 1 finger drags, 2 fingers zoom\nTap here when done" }
                }
            }
        }
        Component {  // families of parallel lines, each rotated about the centre
            id: lines
            Item {
                id: fam
                readonly property real step: win.paperStep
                readonly property var sets: win.paper === "lined" ? [[0, step, 2]]
                    : win.paper === "squared" ? [[0, step, 1], [90, step, 1]]
                    : win.paper === "blueprint" ? [[0, step, 1], [90, step, 1], [0, step * 5, 3], [90, step * 5, 3]]
                    : win.paper === "isometric" ? [[0, step * 0.866, 1], [60, step * 0.866, 1], [120, step * 0.866, 1]] : []
                readonly property real diag: Math.ceil(Math.sqrt(width * width + height * height) / step + 2) * step
                Repeater {
                    model: fam.sets
                    Item {
                        property var set: modelData
                        width: fam.diag; height: fam.diag
                        x: (fam.width - width) / 2; y: (fam.height - height) / 2
                        rotation: set[0]
                        Repeater {
                            model: Math.floor(fam.diag / parent.set[1]) + 1
                            Rectangle {
                                y: index * parent.set[1]; width: parent.width; height: parent.set[2]
                                color: "black"; antialiasing: false
                            }
                        }
                    }
                }
            }
        }
        Component {  // a dot or a small cross at every grid point
            id: marks
            Item {
                id: mk
                readonly property real step: win.paperStep
                readonly property int cols: Math.floor(width / step) + 1
                readonly property bool cross: win.paper === "cross"
                Repeater {
                    model: mk.cols * (Math.floor(mk.height / mk.step) + 1)
                    Item {
                        x: (index % mk.cols) * mk.step; y: Math.floor(index / mk.cols) * mk.step
                        Rectangle { visible: !mk.cross; x: -2; y: -2; width: 4; height: 4; color: "black"; antialiasing: false }
                        Rectangle { visible: mk.cross; x: -7; y: -1; width: 14; height: 2; color: "black"; antialiasing: false }
                        Rectangle { visible: mk.cross; x: -1; y: -7; width: 2; height: 14; color: "black"; antialiasing: false }
                    }
                }
            }
        }

        Item { id: ink; objectName: "ink"; anchors.fill: parent }
        Rectangle { id: epCover; visible: false; anchors.fill: parent; color: "black"; z: 1000 }
        Rectangle {  // one pixel that changes on each refresh, so the scene graph has a frame to send
            id: epNudge; property bool flip: false
            x: view.width - 1; y: view.height - 1; width: 1; height: 1; color: flip ? "#fefefe" : "white"
        }

        Rectangle {  // active area that maps to the monitor
            visible: win.mode === "ink"
            x: win.area[0] * view.width; y: win.area[1] * view.height
            width: (win.area[2] - win.area[0]) * view.width; height: (win.area[3] - win.area[1]) * view.height
            color: "transparent"; border.color: "black"; border.width: 2
        }

        // ---------------------------------------------------------------- finger gestures sheet
        Rectangle {
            id: sheet
            visible: win.mode === "ink" && win.gestureSheet
            readonly property real areaX: win.resL
            readonly property real areaW: view.width - win.resL - win.resR
            width: Math.min(areaW - 80, 960); height: sheetCol.height + 64
            x: areaX + (areaW - width) / 2; y: Math.max(40, (view.height - height) / 2)
            color: "white"; border.width: 4; border.color: "black"; radius: 18
            Column {
                id: sheetCol
                x: 40; y: 32; width: sheet.width - 80; spacing: 0
                Text { text: "FINGER GESTURES"; font.pixelSize: 24; font.bold: true; font.letterSpacing: 4; color: "black"
                       bottomPadding: 18 }
                Repeater {
                    model: win.gestureList
                    Item {
                        width: sheetCol.width; height: 62
                        Rectangle { width: parent.width; height: 2; color: "black"; antialiasing: false }
                        Text { x: 0; y: 2; width: parent.width * 0.48; height: 60; verticalAlignment: Text.AlignVCenter
                               text: modelData[0]; font.pixelSize: 28; font.bold: true; color: "black"; elide: Text.ElideRight }
                        Text { x: parent.width * 0.5; y: 2; width: parent.width * 0.5; height: 60; verticalAlignment: Text.AlignVCenter
                               text: modelData[1]; font.pixelSize: 28; color: "black"; elide: Text.ElideRight }
                    }
                }
                Text { topPadding: 22; text: "Tap anywhere to close"; font.pixelSize: 22; color: "black" }
            }
        }

        // ---------------------------------------------------------------- mask and tracing image panels
        Repeater {
          model: ["mask", "trace"]
          Item {
            id: lp
            readonly property string kind: modelData
            readonly property bool isMask: kind === "mask"
            readonly property string side: isMask ? win.stripSide : win.tstripSide
            readonly property string active: isMask ? win.maskActive : win.traceActive
            readonly property bool firstOn: isMask ? win.maskInvert : win.traceAdjust
            visible: win.mode === "ink" && (isMask ? win.stripAvail && win.stripOpen : win.tstripAvail && win.tstripOpen)
            x: win.sideX(side); width: win.panelPx; height: view.height
            Rectangle { anchors.fill: parent; color: "white" }
            Rectangle { x: lp.side === "right" ? 0 : parent.width - 3; width: 3; height: parent.height; color: "black" }
            Rectangle {  // Invert (the mask in use) / Move (the image, with fingers)
                x: 12; y: 96; width: win.tileW; height: 70; radius: 12
                color: lp.firstOn ? "black" : "white"; border.width: 3; border.color: "black"
                Text { anchors.centerIn: parent; text: lp.isMask ? "Invert" : "Move"; font.pixelSize: 24; font.bold: true
                       color: lp.firstOn ? "white" : "black" }
            }
            Rectangle {  // None
                x: win.narrow ? 12 : 24 + win.tileW; y: win.narrow ? 176 : 96; width: win.tileW; height: 70; radius: 12
                color: lp.active === "" ? "black" : "white"; border.width: 3; border.color: "black"
                Text { anchors.centerIn: parent; text: "None"; font.pixelSize: 24; font.bold: true
                       color: lp.active === "" ? "white" : "black" }
            }
            Item {  // narrow: the tiles scroll inside this
            y: win.narrow ? win.stripTop : 0; width: parent.width; height: win.narrow ? win.listH(lp.kind) : parent.height
            clip: win.narrow
            Repeater {
                model: lp.isMask ? win.maskList : win.traceList
                Item {
                    property bool on: modelData.id === lp.active
                    x: win.narrow ? 12 : 12 + (index % 2) * (win.tileW + 12)
                    y: win.narrow ? index * (win.stripTileH + 10) - win.scrollOf(lp.kind)
                                  : win.stripTop + Math.floor(index / 2) * (win.stripTileH + 10)
                    width: win.tileW; height: win.stripTileH
                    visible: win.narrow || win.tileFits(lp.kind, Math.floor(index / 2))
                    Rectangle { width: parent.width; height: win.stripThumbH; color: "white"
                                border.width: parent.on ? 7 : 2; border.color: "black" }
                    Image { x: 4; y: 4; width: parent.width - 8; height: win.stripThumbH - 8
                            fillMode: lp.isMask ? Image.Stretch : Image.PreserveAspectFit
                            source: modelData.thumb ? "file://" + modelData.thumb : ""; cache: false; smooth: true }
                    Rectangle { y: win.stripThumbH + 4; width: parent.width; height: 38; radius: 8
                                color: parent.on ? "black" : "white" }
                    Text { x: 4; y: win.stripThumbH + 4; width: parent.width - 8; height: 38; verticalAlignment: Text.AlignVCenter
                           horizontalAlignment: Text.AlignHCenter; text: modelData.name; elide: Text.ElideRight
                           font.pixelSize: 20; font.bold: true; color: parent.on ? "white" : "black" }
                }
            }
            }
            Rectangle {  // narrow: where the list is scrolled to, along the panel's outer edge
                readonly property real total: (lp.isMask ? win.maskList : win.traceList).length * (win.stripTileH + 10)
                readonly property real h: win.listH(lp.kind)
                visible: win.narrow && total > h
                x: lp.side === "right" ? parent.width - 7 : 3; width: 4; radius: 2; color: "black"
                y: win.stripTop + (total > 0 ? win.scrollOf(lp.kind) / total * h : 0)
                height: total > 0 ? Math.max(24, h * h / total) : 0
            }
            Rectangle {  // Paper: the pattern under the ink; tap the left half for the previous one, the right half for the next
                visible: lp.isMask
                x: 12; y: win.paperTileY; width: parent.width - 24; height: win.paperTileH; radius: 12
                color: "white"; border.width: 3; border.color: "black"
                Text { x: 0; y: 12; width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "PAPER"
                       font.pixelSize: 17; font.bold: true; font.letterSpacing: 2; color: "black" }
                Text { x: 10; y: 46; text: "◀"; font.pixelSize: 26; color: "black" }
                Text { x: parent.width - 10 - width; y: 46; text: "▶"; font.pixelSize: 26; color: "black" }
                Text { x: 40; y: 46; width: parent.width - 80; height: 40; horizontalAlignment: Text.AlignHCenter
                       verticalAlignment: Text.AlignVCenter; text: win.paperNames[win.paper] || win.paper
                       font.pixelSize: 23; font.bold: true; fontSizeMode: Text.HorizontalFit; minimumPixelSize: 14; color: "black" }
            }
          }
        }

        // ---------------------------------------------------------------- side panels
        Repeater {
          model: ["left", "right"]
          Item {
            id: panel
            readonly property string side: modelData
            readonly property bool main: side === win.mainSide   // has the gestures button and the light bar
            readonly property int first: side === "right" ? 16 : 0
            visible: side === "right" ? win.panelOnR && win.panelOpenR : win.panelOnL && win.panelOpen
            x: win.sideX(side); width: win.panelPx; height: view.height
            Rectangle { anchors.fill: parent; color: "white" }
            Rectangle { x: panel.side === "right" ? 0 : parent.width - 3; width: 3; height: parent.height; color: "black" }
            Item {  // profile row: < name >
                id: prof
                x: 16; y: win.profY; width: parent.width - 32; height: win.profH
                property bool many: win.profileCount > 1
                Rectangle { anchors.fill: parent; radius: 14; border.width: 3; border.color: "black"; color: "white" }
                Text {
                    x: prof.many ? 56 : 12; width: parent.width - 2 * x; anchors.verticalCenter: parent.verticalCenter
                    horizontalAlignment: Text.AlignHCenter; text: win.profileName; font.pixelSize: 26; font.bold: true
                    fontSizeMode: Text.HorizontalFit; minimumPixelSize: 14; elide: Text.ElideRight; color: "black"
                }
                Repeater {
                    model: prof.many ? 2 : 0
                    Item {  // solid triangles from 2 px rows, like the fold tab
                        x: index === 0 ? 16 : prof.width - 16 - 22; anchors.verticalCenter: parent.verticalCenter
                        width: 22; height: 30; rotation: index === 0 ? 180 : 0
                        Repeater {
                            model: 15
                            Rectangle {
                                property real w: 22 * (1 - Math.abs(index - 7) / 7.5)
                                y: index * 2; width: w; height: 2; color: "black"; antialiasing: false
                            }
                        }
                    }
                }
            }
            Rectangle {  // a short message, shown over the profile row for a moment
                visible: win.toast !== ""
                x: 16; y: win.profY; width: parent.width - 32; height: win.profH
                color: "white"; border.color: "black"; border.width: 3; radius: 14
                Text { anchors.fill: parent; anchors.margins: 12; text: win.toast; font.pixelSize: 21; font.bold: true; color: "black"
                       horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
            }
            Item {  // narrow: the buttons scroll inside this
            y: win.narrow ? win.headH : 0; width: parent.width; height: win.narrow ? win.areaOf(panel.side) : parent.height
            clip: win.narrow
            Repeater {
                model: Math.max(0, Math.min(16, win.buttons.length - panel.first))
                Item {
                    id: cell
                    readonly property int gi: panel.first + index   // the number the PC knows it by
                    property var b: win.buttons[gi]
                    property bool none: !b || b.kind === "none"
                    property bool on: win.pressing === gi || (b.kind === "hold" && !!win.latched[gi])
                                      || (b.kind === "pen" && win.penOut) || (b.kind === "snap" && win.snapOn)
                                      || (b.kind === "trace" && win.traceAdjust) || (b.kind === "light" && win.lightOn)
                                      || (b.kind === "mask" && win.maskInvert)
                    x: (index % win.cols) * win.cellW
                    y: win.narrow ? index * win.cellH - win.scrollOf(panel.side) : win.headH + Math.floor(index / 2) * win.cellH
                    width: win.cellW; height: win.cellH
                    Rectangle {
                        visible: !cell.none
                        anchors.fill: parent; anchors.margins: 8
                        radius: 14; border.width: 3; border.color: "black"
                        color: cell.on ? "black" : "white"
                        Column {
                            anchors.centerIn: parent; spacing: 6; width: parent.width - 12
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: cell.b.t
                                   font.pixelSize: 28; font.bold: true; fontSizeMode: Text.HorizontalFit; minimumPixelSize: 16
                                   color: cell.on ? "white" : "black" }
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 18
                                   fontSizeMode: Text.HorizontalFit; minimumPixelSize: 12
                                   text: cell.b.kind === "pen" ? (win.penOut ? "on" : "off") : cell.b.kind === "snap" ? (win.snapOn ? "on" : "off")
                                       : cell.b.kind === "light" ? (win.lightBar ? win.lightPct + "%" : "")
                                       : cell.b.kind === "mask" ? (win.maskInvert ? "inverted" : "normal") : cell.b.kind === "trace" ? (win.traceAdjust ? "moving" : "image") : cell.b.s
                                   color: cell.on ? "white" : "black" }
                        }
                    }
                }
            }
            }
            Rectangle {  // narrow: where the buttons are scrolled to, along the panel's outer edge
                readonly property real total: Math.max(0, Math.min(16, win.buttons.length - panel.first)) * win.cellH
                readonly property real shown: win.areaOf(panel.side)
                visible: win.narrow && total > shown
                x: panel.side === "right" ? parent.width - 7 : 3; width: 4; radius: 2; color: "black"
                y: win.headH + (total > 0 ? win.scrollOf(panel.side) / total * shown : 0)
                height: total > 0 ? Math.max(24, shown * shown / total) : 0
            }
            Rectangle {  // opens the gestures sheet
                visible: panel.main && win.gesturesOn
                x: 16; y: win.gBtnY; width: parent.width - 32; height: win.gBtnH; radius: 14
                border.width: 3; border.color: "black"; color: win.gestureSheet ? "black" : "white"
                Canvas {  // narrow: one ringed dot, like a touch point, instead of the words
                    id: fingerIcon
                    visible: win.narrow
                    anchors.centerIn: parent; width: 56; height: 56
                    property bool inv: win.gestureSheet
                    onInvChanged: requestPaint()
                    onPaint: {
                        var c = getContext("2d"), fg = inv ? "white" : "black"
                        c.reset(); c.lineWidth = 4; c.strokeStyle = fg; c.fillStyle = fg
                        c.beginPath(); c.arc(28, 28, 20, 0, 2 * Math.PI, false); c.stroke()
                        c.beginPath(); c.arc(28, 28, 8, 0, 2 * Math.PI, false); c.fill()
                    }
                }
                Text { anchors.centerIn: parent; width: parent.width - 20; horizontalAlignment: Text.AlignHCenter
                       visible: !win.narrow
                       text: "Finger gestures"; font.pixelSize: 24; font.bold: true; fontSizeMode: Text.HorizontalFit
                       minimumPixelSize: 14; color: win.gestureSheet ? "white" : "black" }
            }
            Item {  // front light: ten steps, black up to the level; the left end turns it off
                visible: panel.main && win.lightBar
                x: 16; y: win.lightY - 34; width: parent.width - 32; height: win.lightH + 34
                Text { x: 6; y: 0; font.pixelSize: 21; font.bold: true; color: "black"; visible: !win.narrow
                       text: win.lightPct > 0 ? "Light " + win.lightPct + "%" : "Light off" }
                Row {
                    y: 34; height: win.lightH; spacing: 4
                    Repeater {
                        model: 10
                        Rectangle {
                            width: (parent.parent.width - 36) / 10; height: win.lightH; radius: 6
                            border.width: 3; border.color: "black"
                            color: (index + 1) * 10 <= win.lightPct ? "black" : "white"
                        }
                    }
                }
            }
        }
        }

        // The corner tabs: one per kind of panel on a side, in a row from that corner. Black while its
        // panel is open. Shapes from plain rectangles, so they stay crisp on e-ink.
        Repeater {
          model: [["left", "keys"], ["left", "mask"], ["left", "trace"], ["right", "keys"], ["right", "mask"], ["right", "trace"]]
          Item {
            id: ctab
            readonly property string side: modelData[0]
            readonly property string kind: modelData[1]
            readonly property int slot: win.kinds(side).indexOf(kind)
            readonly property bool on: win.kindOpen(kind, side)
            readonly property color fg: on ? "white" : "black"
            visible: slot >= 0 && win.tabShown(kind, side)
            x: win.tabX(side, Math.max(0, slot)); y: 0
            width: win.tabS; height: win.tabS
            Rectangle {
                x: 6; y: 6; width: parent.width - 12; height: parent.height - 12; radius: 26
                color: ctab.on ? "black" : "white"; border.width: 3; border.color: "black"
            }
            Repeater {  // shortcuts: four keys
                model: ctab.kind === "keys" ? 4 : 0
                Rectangle { x: ctab.width / 2 - 17 + (index % 2) * 20; y: ctab.height / 2 - 17 + Math.floor(index / 2) * 20
                            width: 14; height: 14; radius: 3; color: ctab.fg; antialiasing: false }
            }
            Rectangle {  // mask: a half-shaded square
                visible: ctab.kind === "mask"
                anchors.centerIn: parent; width: 38; height: 38; color: "transparent"
                border.width: 3; border.color: ctab.fg
                Rectangle { x: 3; y: 3; width: 16; height: 32; color: ctab.fg }
            }
            Rectangle {  // tracing image: a framed picture, a hill and a sun
                visible: ctab.kind === "trace"
                anchors.centerIn: parent; width: 44; height: 34; color: "transparent"
                border.width: 3; border.color: ctab.fg
                Repeater {
                    model: 8
                    Rectangle { x: 7 + (7 - index) * 1.5; y: 12 + index * 2; width: 3 + index * 3; height: 2; color: ctab.fg; antialiasing: false }
                }
                Rectangle { x: 30; y: 7; width: 7; height: 7; color: ctab.fg; antialiasing: false }
            }
          }
        }

        // Fingers: panel buttons, the fold tab and gestures. Mouse events are left alone, so the
        // pen never lands here.
        MultiPointTouchArea {
            anchors.fill: parent
            mouseEnabled: false
            maximumTouchPoints: 10
            onPressed: (pts) => {
                var changed = false
                win.gLastEv = Date.now()
                for (var i = 0; i < pts.length; i++) {
                    var t = pts[i], p = Qt.point(t.x, t.y)
                    console.warn("LOG:touch " + Math.round(t.x) + "," + Math.round(t.y) + " size " + Math.round(win.touchSize(t)))
                    if (win.gestureSheet && !win.inPanel(p)) {  // a tap closes the sheet and does nothing else
                        win.gestureSheet = false
                        var tbx = win.touchBtn; tbx[t.pointId] = -1; win.touchBtn = tbx
                        continue
                    }
                    var sk = win.scrollKeyAt(p)
                    if (sk !== "") {  // narrow: a drag scrolls, a tap presses when the finger lifts
                        var tbd = win.touchBtn; tbd[t.pointId] = -7; win.touchBtn = tbd
                        var dd = win.drags
                        dd[t.pointId] = {key: sk, y0: t.y, s0: win.scrollOf(sk), p: p, moved: false, pressed: false, btn: -1}
                        win.drags = dd
                        dragHold.restart()
                        continue
                    }
                    var u = win.uiAt(p)
                    if (u && u.k !== "keys") {  // a mask or image tile, or their tab: done at once, the finger does nothing more
                        var tbs = win.touchBtn; tbs[t.pointId] = -1; win.touchBtn = tbs
                        win.stripTouch(u, p)
                        continue
                    }
                    if (win.inPanel(p)) {  // the panel answers even with the pen hovering: the other hand taps it
                        var tb = win.touchBtn; tb[t.pointId] = win.pressAt(p); win.touchBtn = tb
                        continue
                    }
                    if (win.palmCheck(t)) { changed = true; continue }
                    var g = win.gPts; g[t.pointId] = {x: t.x, y: t.y}; win.gPts = g
                    var st = win.gStart; st[t.pointId] = {x: t.x, y: t.y}; win.gStart = st
                    changed = true
                }
                if (changed) { win.fingersChanged(); win.sendTouch() }
            }
            onUpdated: (pts) => {
                var g = win.gPts, moved = false, palm = false
                win.gLastEv = Date.now()
                for (var i = 0; i < pts.length; i++) {
                    var t = pts[i]
                    if (win.touchBtn[t.pointId] === -7) {  // narrow: scrolling a panel
                        var dg = win.drags[t.pointId]
                        if (dg && !dg.pressed) {
                            if (!dg.moved && Math.abs(t.y - dg.y0) > 16) dg.moved = true
                            if (dg.moved) win.setScroll(dg.key, dg.s0 - (t.y - dg.y0))
                        }
                        continue
                    }
                    if (win.touchBtn[t.pointId] === -5) {  // a finger sliding along the light bar
                        var lp = Qt.point(t.x, t.y)
                        if (win.lightHit(lp)) win.lightAt(lp)
                        continue
                    }
                    if (g[t.pointId] && win.palmCheck(t)) { palm = true; continue }
                    if (g[t.pointId]) { g[t.pointId] = {x: t.x, y: t.y}; moved = true }
                }
                if (palm) { win.fingersChanged(); win.sendTouch(); return }
                if (moved) { win.gPts = g; win.fingersMoved(); win.sendTouch() }
            }
            onReleased: (pts) => {
                var g = win.gPts, changed = false
                win.gLastEv = Date.now()
                for (var i = 0; i < pts.length; i++) {
                    var t = pts[i]
                    if (win.palms[t.pointId]) {
                        var pl = win.palms; delete pl[t.pointId]; win.palms = pl
                        if (Object.keys(g).length === 0) changed = true
                        continue
                    }
                    if (t.pointId in win.touchBtn) {
                        var tb = win.touchBtn
                        if (tb[t.pointId] === -7) {
                            var dr = win.drags, de = dr[t.pointId]
                            delete dr[t.pointId]; win.drags = dr
                            if (de && de.pressed) { if (de.btn >= 0) win.releaseBtn(de.btn, false) }
                            else if (de && !de.moved) {
                                if (de.key === "mask" || de.key === "trace") win.stripTouch(win.uiAt(de.p), de.p)
                                else { var bi = win.pressAt(de.p); if (bi >= 0) win.releaseBtn(bi, false) }
                            }
                        }
                        if (tb[t.pointId] >= 0) win.releaseBtn(tb[t.pointId], false)
                        delete tb[t.pointId]; win.touchBtn = tb
                        continue
                    }
                    if (g[t.pointId]) {
                        if (win.gMode === "three") win.fingersUp()
                        delete g[t.pointId]; changed = true
                    }
                }
                if (changed) { win.gPts = g; win.fingersChanged(); win.sendTouch() }
            }
            onCanceled: (pts) => { win.drags = ({}); win.endGesture(); win.gPts = ({}); win.palms = ({}); win.fingersChanged(); win.sendTouch(); win.pressing = -1 }
        }

        Repeater {  // 9 calibration crosshairs, reading order, 10% inset (matches the PDF sheet)
            model: win.mode === "targets" ? 9 : 0
            Item {
                property real u: [0.1, 0.5, 0.9][index % 3]
                property real v: [0.1, 0.5, 0.9][Math.floor(index / 3)]
                property bool hot: win.nextTarget === index + 1
                x: u * view.width; y: v * view.height
                Rectangle { x: -40; y: -1.5; width: 80; height: 3; color: "black" }
                Rectangle { x: -1.5; y: -40; width: 3; height: 80; color: "black" }
                Rectangle { x: -14; y: -14; width: 28; height: 28; color: "transparent"; border.width: 2; border.color: "black" }
                Rectangle { visible: hot; x: -34; y: -34; width: 68; height: 68; radius: 34
                            color: "transparent"; border.width: 6; border.color: "black" }
                Text { x: 22; y: v > 0.6 ? -60 : 22; text: index + 1; font.pixelSize: hot ? 44 : 30; font.bold: hot }
            }
        }

        Text {
            visible: win.mode === "targets"
            anchors.centerIn: parent; anchors.verticalCenterOffset: view.height * 0.2
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: 34
            text: win.nextTarget > 0 ? "Tap the centre of crosshair " + win.nextTarget : "Calibration targets"
        }

        Text {
            visible: !win.panelOn
            x: 30; y: 20
            font.pixelSize: 26; color: "black"
            text: win.status + "    (power button: back to notebooks)"
        }
    }
}
)QML";

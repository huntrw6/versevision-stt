import Cocoa
import ApplicationServices
func now() -> Double { Date().timeIntervalSince1970 }
func attr(_ e: AXUIElement, _ a: String) -> AnyObject? { var v: CFTypeRef?; return AXUIElementCopyAttributeValue(e, a as CFString, &v) == .success ? (v as AnyObject?) : nil }
func kids(_ e: AXUIElement) -> [AXUIElement] { (attr(e, kAXChildrenAttribute) as? [AXUIElement]) ?? [] }
func s(_ e: AXUIElement, _ a: String) -> String { (attr(e, a) as? String) ?? "" }
func frame(_ e: AXUIElement) -> CGRect? {
    guard let p = attr(e, kAXPositionAttribute), let z = attr(e, kAXSizeAttribute) else { return nil }
    var pt = CGPoint.zero, sz = CGSize.zero; AXValueGetValue(p as! AXValue, .cgPoint, &pt); AXValueGetValue(z as! AXValue, .cgSize, &sz); return CGRect(origin: pt, size: sz)
}
func find(_ e: AXUIElement, _ d: Int, _ p: (AXUIElement) -> Bool) -> AXUIElement? { if p(e) { return e }; if d > 16 { return nil }; for c in kids(e) { if let r = find(c, d + 1, p) { return r } }; return nil }
func findAll(_ e: AXUIElement, _ d: Int, _ p: (AXUIElement) -> Bool, _ out: inout [AXUIElement]) { if p(e) { out.append(e) }; if d > 16 { return }; for c in kids(e) { findAll(c, d + 1, p, &out) } }
func click(_ p: CGPoint) { for t in [CGEventType.leftMouseDown, .leftMouseUp] { CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap) } }
func key(_ code: CGKeyCode) { for d in [true, false] { CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: d)?.post(tap: .cghidEventTap) } }
func api(_ path: String) -> [String: Any]? { guard let u = URL(string: "http://127.0.0.1:1025" + path), let d = try? Data(contentsOf: u) else { return nil }; return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] }


// vvbible: a long-running helper that drives ProPresenter's Bible panel. Commands arrive one per line on stdin, answers leave as one
// JSON line each on stdout. Staying alive avoids ~400 ms of start-up per command, so clicking a result card takes about 10 ms.
//   lookup <text>       type a reference into the lookup box and wait for the results (nothing goes on screen)
//   click <n>           put result card n (1 = first) on the output
//   show                switch ProPresenter to the Show view          bible   switch to the Bible view
//   version <name>      choose a Bible version in the drop-down      ping    answer at once
//   quit
setvbuf(stdout, nil, _IOLBF, 0)
guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: "com.renewedvision.propresenter").first else { print("{\"ok\":false,\"error\":\"ProPresenter not running\"}"); exit(1) }
let ax = AXUIElementCreateApplication(app.processIdentifier)
func frontPid() -> pid_t {
    let sys = AXUIElementCreateSystemWide(); var v: CFTypeRef?
    guard AXUIElementCopyAttributeValue(sys, kAXFocusedApplicationAttribute as CFString, &v) == .success, let e = v else { return -1 }
    var pid: pid_t = -1; AXUIElementGetPid(e as! AXUIElement, &pid); return pid
}
func bringToFront() { if frontPid() == app.processIdentifier { return }; app.activate(options: [.activateIgnoringOtherApps]); let dl = now() + 1.5; while now() < dl && frontPid() != app.processIdentifier { RunLoop.current.run(until: Date().addingTimeInterval(0.002)) } }
func mainWindow() -> AXUIElement? { ((attr(ax, kAXWindowsAttribute) as? [AXUIElement]) ?? []).max(by: { (frame($0).map { $0.width * $0.height } ?? 0) < (frame($1).map { $0.width * $0.height } ?? 0) }) }
func parent(_ e: AXUIElement) -> AXUIElement? { attr(e, kAXParentAttribute).map { $0 as! AXUIElement } }
func jsonOut(_ d: [String: Any]) { if let data = try? JSONSerialization.data(withJSONObject: d), let s = String(data: data, encoding: .utf8) { print(s) } }
func typeText(_ t: String) { for ch in t.utf16 { var c = ch; for d in [true, false] { let ev = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: d); ev?.keyboardSetUnicodeString(stringLength: 1, unicodeString: &c); ev?.post(tap: .cghidEventTap) } } }

struct Panel { var win: AXUIElement; var area: AXUIElement; var lookup: AXUIElement; var results: CGRect }
var cached: Panel? = nil
func isBibleOpen(_ win: AXUIElement) -> Bool { find(win, 0, { s($0, kAXRoleAttribute) == "AXButton" && s($0, kAXDescriptionAttribute) == "search" }) != nil }
func findPanel() -> Panel? {
    guard let win = mainWindow() else { return nil }
    guard let sb = find(win, 0, { s($0, kAXRoleAttribute) == "AXButton" && s($0, kAXDescriptionAttribute) == "search" }), let sf = frame(sb) else { return nil }
    let wf = frame(win) ?? CGRect(x: 0, y: 0, width: 1600, height: 1000)
    var cur: AXUIElement? = sb; var area: AXUIElement? = nil
    while let c = cur { if s(c, kAXRoleAttribute) == "AXGroup", let f = frame(c), f.height > wf.height * 0.5, f.width > wf.width * 0.3 { area = c; break }; cur = parent(c) }
    guard let a = area else { return nil }
    var tf: [AXUIElement] = []
    findAll(win, 0, { e in s(e, kAXRoleAttribute) == "AXTextField" && s(e, kAXSubroleAttribute) != "AXSearchField" && (frame(e).map { $0.width > 150 && abs($0.midY - sf.midY) < 14 && $0.maxX <= sf.minX + 5 } ?? false) }, &tf)
    guard let look = tf.max(by: { (frame($0)?.maxX ?? 0) < (frame($1)?.maxX ?? 0) }) else { return nil }
    let af = frame(a) ?? wf
    var scrolls: [AXUIElement] = []
    findAll(a, 0, { s($0, kAXRoleAttribute) == "AXScrollArea" && (frame($0).map { $0.width > af.width * 0.6 && $0.height > wf.height * 0.4 } ?? false) }, &scrolls)
    guard let r = scrolls.first.flatMap({ frame($0) }) else { return nil }
    return Panel(win: win, area: a, lookup: look, results: r)
}
func panel(open: Bool = true) -> Panel? {
    if let p = cached, isBibleOpen(p.win), frame(p.lookup) != nil { return p }       // elements are reused while the window is unchanged
    cached = nil
    if open, let win = mainWindow(), !isBibleOpen(win), let b = find(win, 0, { s($0, kAXRoleAttribute) == "AXRadioButton" && s($0, kAXDescriptionAttribute) == "Bible" }) {
        AXUIElementPerformAction(b, kAXPressAction as CFString)
        let dl = now() + 2; while now() < dl && !isBibleOpen(win) { usleep(8_000) }
    }
    cached = findPanel(); return cached
}
func busy(_ p: Panel) -> Bool { kids(p.area).contains { s($0, kAXRoleAttribute) == "AXButton" && s($0, kAXDescriptionAttribute) == "stop progress" } }
func cardCenter(_ p: Panel, _ n: Int) -> CGPoint {          // cards are 333 x 205 with 13 / 15 px gaps, starting 22 / 14 px inside the results area
    let r = p.results; let cols = max(1, Int((r.width - 22 + 13) / 346)); let i = n - 1
    return CGPoint(x: r.minX + 22 + CGFloat(i % cols) * 346 + 166, y: r.minY + 14 + CGFloat(i / cols) * 220 + 100)
}
func versionPopup(_ p: Panel) -> AXUIElement? {
    guard let lf = frame(p.lookup) else { return nil }
    var pops: [AXUIElement] = []
    findAll(p.win, 0, { e in s(e, kAXRoleAttribute) == "AXPopUpButton" && (frame(e).map { abs($0.minX - lf.minX) < 25 && $0.minY > lf.maxY - 5 && $0.minY < lf.maxY + 70 && $0.width > 150 } ?? false) }, &pops)
    return pops.first
}

while let line = readLine() {
    let t0 = now()
    let parts = line.split(separator: " ", maxSplits: 1).map(String.init)
    guard let cmd = parts.first else { continue }
    let arg = parts.count > 1 ? parts[1] : ""
    var out: [String: Any] = ["cmd": cmd]
    switch cmd {
    case "ping": out["ok"] = true
    case "quit": jsonOut(["ok": true]); exit(0)
    case "lookup":
        bringToFront()
        guard let p = panel() else { out["ok"] = false; out["error"] = "Bible panel not found"; break }
        AXUIElementSetAttributeValue(p.lookup, kAXFocusedAttribute as CFString, kCFBooleanTrue)
        AXUIElementSetAttributeValue(p.lookup, kAXValueAttribute as CFString, "" as CFString)
        typeText(arg); key(36)
        var started = false; let d1 = now() + 0.30
        while now() < d1 { if busy(p) { started = true; break }; usleep(1_000) }
        if started { let d2 = now() + 4; while now() < d2 && busy(p) { usleep(1_000) } } else { usleep(60_000) }
        out["ok"] = true
    case "click":
        bringToFront()
        guard let p = panel(), let n = Int(arg), n >= 1 else { out["ok"] = false; out["error"] = "no panel or bad card"; break }
        click(cardCenter(p, n)); out["ok"] = true
    case "show":
        bringToFront()
        if let win = mainWindow(), let b = find(win, 0, { s($0, kAXRoleAttribute) == "AXRadioButton" && s($0, kAXDescriptionAttribute) == "Show" }) { AXUIElementPerformAction(b, kAXPressAction as CFString); cached = nil; out["ok"] = true } else { out["ok"] = false }
    case "bible":
        bringToFront(); out["ok"] = panel() != nil
    case "add":
        bringToFront()
        guard let p = panel() else { out["ok"] = false; out["error"] = "no panel"; break }
        guard let saveAs = find(p.win, 0, { s($0, kAXRoleAttribute) == "AXMenuButton" && (s($0, kAXDescriptionAttribute) == "Save As…" || s($0, kAXTitleAttribute) == "Save As…") }) else { out["ok"] = false; out["error"] = "Save As not found"; break }
        var done = false
        for _ in 0..<3 {
            AXUIElementPerformAction(saveAs, kAXPressAction as CFString)
            var item: AXUIElement? = nil; let d2 = now() + 0.8
            while item == nil && now() < d2 { item = find(saveAs, 0, { s($0, kAXRoleAttribute) == "AXMenuItem" && s($0, kAXTitleAttribute) == "Copy to Selected Presentation" }); if item == nil { usleep(3_000) } }
            if let it = item { AXUIElementPerformAction(it, kAXPressAction as CFString); done = true; break }
            key(53); usleep(60_000)
        }
        out["ok"] = done
    case "version":
        bringToFront()
        guard let p = panel(), let pop = versionPopup(p) else { out["ok"] = false; out["error"] = "version menu not found"; break }
        let was = s(pop, kAXValueAttribute)
        if was == arg { out["ok"] = true; out["was"] = was; break }
        AXUIElementPerformAction(pop, kAXPressAction as CFString)
        var items: [AXUIElement] = []; let dl = now() + 1
        while items.isEmpty && now() < dl { findAll(pop, 0, { s($0, kAXRoleAttribute) == "AXMenuItem" }, &items); if items.isEmpty { usleep(3_000) } }
        if let it = items.first(where: { s($0, kAXTitleAttribute) == arg }) {
            AXUIElementPerformAction(it, kAXPressAction as CFString)
            let d2 = now() + 1; while s(pop, kAXValueAttribute) != arg && now() < d2 { usleep(5_000) }
            out["ok"] = s(pop, kAXValueAttribute) == arg; out["was"] = was
        } else { key(53); out["ok"] = false; out["error"] = "no such version" }
    default: out["ok"] = false; out["error"] = "unknown command"
    }
    out["ms"] = Int((now() - t0) * 1000)
    jsonOut(out)
}

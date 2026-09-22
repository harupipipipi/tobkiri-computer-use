import Cocoa
import WebKit

struct ProbeCounters {
    var leftDown = 0
    var leftUp = 0
    var rightDown = 0
    var rightUp = 0
    var contextMenu = 0
    var middleDown = 0
    var middleUp = 0
    var middleClick = 0
    var wheel = 0
    var wheelDeltaX = 0.0
    var wheelDeltaY = 0.0

    mutating func add(_ event: String, deltaX: Double = 0, deltaY: Double = 0) {
        switch event {
        case "left_down": leftDown += 1
        case "left_up": leftUp += 1
        case "right_down": rightDown += 1
        case "right_up": rightUp += 1
        case "contextmenu": contextMenu += 1
        case "middle_down": middleDown += 1
        case "middle_up": middleUp += 1
        case "middle_click": middleClick += 1
        case "wheel":
            wheel += 1
            wheelDeltaX += deltaX
            wheelDeltaY += deltaY
        default: break
        }
    }

    func json() -> [String: Any] {
        [
            "left_down": leftDown, "left_up": leftUp,
            "right_down": rightDown, "right_up": rightUp,
            "contextmenu": contextMenu,
            "middle_down": middleDown, "middle_up": middleUp, "middle_click": middleClick,
            "wheel": wheel, "wheel_delta_x": wheelDeltaX, "wheel_delta_y": wheelDeltaY,
        ]
    }

    mutating func reset() { self = ProbeCounters() }
}

func counterDeltas(for native: NSEvent) -> (x: Double, y: Double) {
    guard native.type == .scrollWheel else { return (0, 0) }
    return (Double(native.scrollingDeltaX), Double(native.scrollingDeltaY))
}

func nativeEventFields(_ native: NSEvent) -> [String: Any] {
    let point = native.locationInWindow
    var fields: [String: Any] = ["x": point.x, "y": point.y]
    switch native.type {
    case .scrollWheel:
        fields["scrolling_delta_x"] = native.scrollingDeltaX
        fields["scrolling_delta_y"] = native.scrollingDeltaY
        fields["precise_scroll"] = native.hasPreciseScrollingDeltas
        fields["phase"] = native.phase.rawValue
    case .leftMouseDown, .leftMouseUp, .rightMouseDown, .rightMouseUp,
         .otherMouseDown, .otherMouseUp:
        fields["button_number"] = native.buttonNumber
        fields["click_count"] = native.clickCount
    default:
        break
    }
    return fields
}

struct ProbeLogDiagnostics {
    let pending: Int
    let dropped: Int
    let failures: Int
    let accepting: Bool

    var summary: String {
        "log q:\(pending) drop:\(dropped) fail:\(failures)\(accepting ? "" : " closed")"
    }
}

final class JSONLLogger {
    static let maximumPending = 8192

    let url: URL
    private let queue = DispatchQueue(label: "local.tobkiri.pointer-probe-jsonl")
    private let stateLock = NSLock()
    private var handle: FileHandle?
    private var pending = 0
    private var dropped = 0
    private var failures = 0
    private var accepting = true
    private var unavailable = false

    init(url: URL) { self.url = url }

    func diagnostics() -> ProbeLogDiagnostics {
        stateLock.lock()
        defer { stateLock.unlock() }
        return ProbeLogDiagnostics(pending: pending, dropped: dropped, failures: failures,
                                   accepting: accepting)
    }

    func record(region: String, callback: String, event: String, window: NSWindow?,
                counters: [String: Any], native: NSEvent? = nil, extra: [String: Any] = [:]) {
        var row: [String: Any] = [
            "region": region,
            "callback": callback,
            "event": event,
            "time": ProcessInfo.processInfo.systemUptime,
            "window_number": window?.windowNumber ?? -1,
            "app_active": NSApp.isActive,
            "window_key": window?.isKeyWindow ?? false,
            "counts": counters,
        ]
        if let native { row.merge(nativeEventFields(native), uniquingKeysWith: { _, latest in latest }) }
        for (key, value) in extra { row[key] = value }
        append(row)
    }

    func close() {
        stateLock.lock()
        accepting = false
        stateLock.unlock()
        queue.async {
            if let handle = self.handle {
                try? handle.close()
                self.handle = nil
            }
        }
    }

    private func append(_ row: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(row),
              var data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]) else {
            recordFailure()
            return
        }
        data.append(10)
        stateLock.lock()
        guard accepting, pending < Self.maximumPending else {
            dropped += 1
            stateLock.unlock()
            return
        }
        pending += 1
        // Submit while holding the state lock so close() is queued after every
        // accepted record.  The serial worker therefore never reopens after it
        // has processed its close block.
        queue.async { self.write(data) }
        stateLock.unlock()
    }

    private func recordFailure(unavailable: Bool = false) {
        stateLock.lock()
        failures += 1
        if unavailable { self.unavailable = true }
        stateLock.unlock()
    }

    private func complete() {
        stateLock.lock()
        pending -= 1
        stateLock.unlock()
    }

    private func openIfNeeded() throws {
        if handle != nil { return }
        if unavailable {
            throw NSError(domain: "TobkiriPointerProbeLogger", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "writer unavailable"])
        }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path),
           !FileManager.default.createFile(atPath: url.path, contents: nil) {
            throw NSError(domain: "TobkiriPointerProbeLogger", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "could not create log file"])
        }
        let opened = try FileHandle(forWritingTo: url)
        try opened.seekToEnd()
        handle = opened
    }

    private func write(_ data: Data) {
        defer { complete() }
        do {
            try openIfNeeded()
            guard let handle else {
                throw NSError(domain: "TobkiriPointerProbeLogger", code: 3,
                              userInfo: [NSLocalizedDescriptionKey: "missing log handle"])
            }
            try handle.write(contentsOf: data)
        } catch {
            try? handle?.close()
            handle = nil
            recordFailure(unavailable: true)
        }
    }
}

func eventLogURL() -> URL {
    let arguments = CommandLine.arguments
    if let index = arguments.firstIndex(of: "--event-log") {
        if index + 1 < arguments.count {
            let path = arguments[index + 1]
            if path.hasPrefix("/") { return URL(fileURLWithPath: path) }
        }
        FileHandle.standardError.write(Data("Ignoring non-absolute --event-log; using Library/Caches fixture log.\n".utf8))
    }
    return URL(fileURLWithPath: NSHomeDirectory())
        .appendingPathComponent("Library/Caches/tobkiri-computer-use/fixture-logs")
        .appendingPathComponent("pointer-probe-\(ProcessInfo.processInfo.processIdentifier).jsonl")
}

final class NativeProbeView: NSView {
    var counters = ProbeCounters()
    var onEvent: ((String, ProbeCounters, NSEvent) -> Void)?
    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        setAccessibilityElement(true)
        setAccessibilityRole(.group)
        setAccessibilityLabel("AppKit pointer event region")
        setAccessibilityHelp("Scrollable native test region that records pointer callbacks.")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) unavailable") }

    func record(_ name: String, event: NSEvent) {
        let delta = counterDeltas(for: event)
        counters.add(name, deltaX: delta.x, deltaY: delta.y)
        onEvent?(name, counters, event)
        DispatchQueue.main.async { self.needsDisplay = true }
    }

    override func mouseDown(with event: NSEvent) { record("left_down", event: event) }
    override func mouseUp(with event: NSEvent) { record("left_up", event: event) }
    override func rightMouseDown(with event: NSEvent) {
        record("right_down", event: event)
        super.rightMouseDown(with: event)
    }
    override func rightMouseUp(with event: NSEvent) { record("right_up", event: event) }
    override func otherMouseDown(with event: NSEvent) {
        record(event.buttonNumber == 2 ? "middle_down" : "other_down", event: event)
    }
    override func otherMouseUp(with event: NSEvent) {
        record(event.buttonNumber == 2 ? "middle_up" : "other_up", event: event)
    }
    override func scrollWheel(with event: NSEvent) {
        record("wheel", event: event)
        super.scrollWheel(with: event)
    }
    override func menu(for event: NSEvent) -> NSMenu? {
        record("contextmenu", event: event)
        return nil
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.white.setFill()
        bounds.fill()
        NSColor(calibratedWhite: 0.78, alpha: 1).setStroke()
        NSBezierPath(rect: bounds.insetBy(dx: 0.5, dy: 0.5)).stroke()
        let copy = "Scrollable native empty area. Right-click records callback; no menu is forced."
        copy.draw(at: NSPoint(x: 16, y: 16), withAttributes: [
            .font: NSFont.systemFont(ofSize: 13), .foregroundColor: NSColor.secondaryLabelColor,
        ])
        let lower = "Scroll to measure actual NSScrollView position."
        lower.draw(at: NSPoint(x: 16, y: bounds.height - 36), withAttributes: [
            .font: NSFont.systemFont(ofSize: 13), .foregroundColor: NSColor.secondaryLabelColor,
        ])
    }
}

final class PointerProbeController: NSObject, WKScriptMessageHandler {
    let logger: JSONLLogger
    let nativeStatus = NSTextField(labelWithString: "")
    let webStatus = NSTextField(labelWithString: "")
    let windowStatus = NSTextField(labelWithString: "")
    let nativeView = NativeProbeView(frame: NSRect(x: 0, y: 0, width: 450, height: 860))
    let nativeScroll = NSScrollView()
    var webCounts: [String: Any] = [:]
    weak var window: NSWindow?
    var webView: WKWebView!

    init(logger: JSONLLogger) {
        self.logger = logger
        super.init()
        nativeView.onEvent = { [weak self] event, counters, native in
            guard let self else { return }
            self.logger.record(region: "appkit", callback: self.callbackName(event), event: event,
                               window: self.window, counters: counters.json(), native: native)
            self.refreshNative()
            self.refreshWindowState()
        }
    }

    func callbackName(_ event: String) -> String {
        switch event {
        case "left_down": return "mouseDown"
        case "left_up": return "mouseUp"
        case "right_down": return "rightMouseDown"
        case "right_up": return "rightMouseUp"
        case "contextmenu": return "menu(for:)"
        case "middle_down": return "otherMouseDown"
        case "middle_up": return "otherMouseUp"
        case "wheel": return "scrollWheel"
        default: return event
        }
    }

    func configureWebView(frame: NSRect, html: URL) {
        let controller = WKUserContentController()
        controller.add(self, name: "pointerProbe")
        let configuration = WKWebViewConfiguration()
        configuration.userContentController = controller
        webView = WKWebView(frame: frame, configuration: configuration)
        webView.setAccessibilityLabel("WKWebView pointer event region")
        webView.loadFileURL(html, allowingReadAccessTo: html.deletingLastPathComponent())
    }

    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard message.name == "pointerProbe", let body = message.body as? [String: Any],
              let event = body["event"] as? String else { return }
        let counts = body["counts"] as? [String: Any] ?? [:]
        webCounts = counts
        var extra: [String: Any] = [
            "dom_type": body["dom_type"] ?? event,
            "button_number": body["button"] ?? -1,
            "scroll_top": body["scroll_top"] ?? 0,
        ]
        if let deltaX = body["delta_x"] { extra["scrolling_delta_x"] = deltaX }
        if let deltaY = body["delta_y"] { extra["scrolling_delta_y"] = deltaY }
        logger.record(region: "wkwebview", callback: "DOM \(body["dom_type"] ?? event)",
                      event: event, window: window, counters: counts, extra: extra)
        refreshWeb(scrollTop: body["scroll_top"])
        refreshWindowState()
    }

    func refreshNative() {
        DispatchQueue.main.async {
            let c = self.nativeView.counters
            let scroll = self.nativeScroll.contentView.bounds.origin.y
            self.nativeStatus.stringValue =
                "AppKit L \(c.leftDown)/\(c.leftUp) · R \(c.rightDown)/\(c.rightUp) · menu \(c.contextMenu) · M \(c.middleDown)/\(c.middleUp) · wheel \(c.wheel) Δ \(String(format: "%.1f", c.wheelDeltaY)) · scroll \(String(format: "%.1f", scroll))"
        }
    }

    func refreshWeb(scrollTop: Any? = nil) {
        DispatchQueue.main.async {
            let c = self.webCounts
            let top = scrollTop ?? c["scroll_top"] ?? 0
            self.webStatus.stringValue =
                "WK L \(c["left_down"] ?? 0)/\(c["left_up"] ?? 0) · R \(c["right_down"] ?? 0)/\(c["right_up"] ?? 0) · menu \(c["contextmenu"] ?? 0) · M \(c["middle_down"] ?? 0)/\(c["middle_up"] ?? 0) · wheel \(c["wheel"] ?? 0) Δ \(c["wheel_delta_y"] ?? 0) · scroll \(top)"
        }
    }

    func refreshWindowState() {
        DispatchQueue.main.async {
            let log = self.logger.diagnostics().summary
            self.windowStatus.stringValue =
                "JSONL: \(self.logger.url.path) · \(log) · window \(self.window?.windowNumber ?? -1) · active \(NSApp.isActive) · key \(self.window?.isKeyWindow ?? false) (recorded state, not independent focus proof)"
        }
    }

    @objc func clear() {
        nativeView.counters.reset()
        webCounts = [:]
        webView.evaluateJavaScript("window.pointerProbeReset && window.pointerProbeReset()")
        logger.record(region: "fixture", callback: "clear", event: "reset", window: window,
                      counters: ["appkit": nativeView.counters.json(), "wkwebview": webCounts])
        refreshNative()
        refreshWeb()
        refreshWindowState()
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
var probeLogger: JSONLLogger?
final class ProbeDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        probeLogger?.close()
    }
}
let delegate = ProbeDelegate()
app.delegate = delegate

do {
    let logger = JSONLLogger(url: eventLogURL())
    probeLogger = logger
    let controller = PointerProbeController(logger: logger)
    let w = NSWindow(contentRect: NSRect(x: 160, y: 180, width: 1010, height: 670),
                     styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
    controller.window = w
    w.title = "Tobkiri Pointer Probe Fixture"
    w.isReleasedWhenClosed = false
    w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

    let root = NSView(frame: NSRect(x: 0, y: 0, width: 1010, height: 670))
    w.contentView = root
    let heading = NSTextField(labelWithString: "Pointer delivery probe: two independently counted regions")
    heading.font = .boldSystemFont(ofSize: 20)
    heading.frame = NSRect(x: 20, y: 630, width: 900, height: 26)
    root.addSubview(heading)

    let nativeHeading = NSTextField(labelWithString: "AppKit NSView callbacks")
    nativeHeading.font = .boldSystemFont(ofSize: 15)
    nativeHeading.frame = NSRect(x: 20, y: 596, width: 440, height: 20)
    root.addSubview(nativeHeading)
    controller.nativeStatus.frame = NSRect(x: 20, y: 570, width: 470, height: 18)
    controller.nativeStatus.font = .monospacedSystemFont(ofSize: 10, weight: .regular)
    root.addSubview(controller.nativeStatus)
    controller.nativeScroll.frame = NSRect(x: 20, y: 112, width: 470, height: 450)
    controller.nativeScroll.hasVerticalScroller = true
    controller.nativeScroll.autohidesScrollers = false
    controller.nativeScroll.borderType = .lineBorder
    controller.nativeScroll.documentView = controller.nativeView
    controller.nativeScroll.contentView.postsBoundsChangedNotifications = true
    NotificationCenter.default.addObserver(forName: NSView.boundsDidChangeNotification,
                                           object: controller.nativeScroll.contentView, queue: .main) { [weak controller] _ in
        controller?.refreshNative()
    }
    root.addSubview(controller.nativeScroll)

    let webHeading = NSTextField(labelWithString: "WKWebView DOM callbacks (local HTML)")
    webHeading.font = .boldSystemFont(ofSize: 15)
    webHeading.frame = NSRect(x: 520, y: 596, width: 440, height: 20)
    root.addSubview(webHeading)
    controller.webStatus.frame = NSRect(x: 520, y: 570, width: 470, height: 18)
    controller.webStatus.font = .monospacedSystemFont(ofSize: 10, weight: .regular)
    root.addSubview(controller.webStatus)
    guard let html = Bundle.main.url(forResource: "pointer-probe", withExtension: "html") else {
        throw NSError(domain: "PointerProbe", code: 3,
                      userInfo: [NSLocalizedDescriptionKey: "Missing bundled pointer-probe.html"])
    }
    controller.configureWebView(frame: NSRect(x: 520, y: 112, width: 470, height: 450), html: html)
    root.addSubview(controller.webView)

    let clear = NSButton(title: "Clear pointer counters", target: controller,
                         action: #selector(PointerProbeController.clear))
    clear.setAccessibilityLabel("Clear pointer counters")
    clear.frame = NSRect(x: 20, y: 68, width: 180, height: 30)
    root.addSubview(clear)
    controller.windowStatus.frame = NSRect(x: 20, y: 28, width: 960, height: 24)
    controller.windowStatus.font = .systemFont(ofSize: 10)
    root.addSubview(controller.windowStatus)
    controller.refreshNative()
    controller.refreshWeb()
    controller.refreshWindowState()
    Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak controller] _ in
        controller?.refreshWindowState()
    }
    w.orderFrontRegardless()
    app.run()
} catch {
    FileHandle.standardError.write(Data("Pointer probe setup failed: \(error)\n".utf8))
    exit(2)
}

import Cocoa

struct FixtureLogDiagnostics {
    let pending: Int
    let dropped: Int
    let failures: Int
    let accepting: Bool

    var summary: String {
        "log q:\(pending) drop:\(dropped) fail:\(failures)\(accepting ? "" : " closed")"
    }
}

final class AsyncJSONLWriter {
    static let maximumPending = 8192

    let url: URL
    private let queue = DispatchQueue(label: "local.tobkiri.fixture-jsonl")
    private let stateLock = NSLock()
    private var handle: FileHandle?
    private var pending = 0
    private var dropped = 0
    private var failures = 0
    private var accepting = true
    private var unavailable = false

    init(url: URL) { self.url = url }

    func diagnostics() -> FixtureLogDiagnostics {
        stateLock.lock()
        defer { stateLock.unlock() }
        return FixtureLogDiagnostics(pending: pending, dropped: dropped, failures: failures,
                                     accepting: accepting)
    }

    func append(_ object: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(object),
              var data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
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
            throw NSError(domain: "TobkiriFixtureLogger", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "writer unavailable"])
        }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path),
           !FileManager.default.createFile(atPath: url.path, contents: nil) {
            throw NSError(domain: "TobkiriFixtureLogger", code: 2,
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
            try handle?.write(contentsOf: data)
        } catch {
            try? handle?.close()
            handle = nil
            recordFailure(unavailable: true)
        }
    }
}

func drawingEventLogURL() -> URL {
    let arguments = CommandLine.arguments
    if let index = arguments.firstIndex(of: "--event-log"), index + 1 < arguments.count {
        let path = arguments[index + 1]
        if path.hasPrefix("/") { return URL(fileURLWithPath: path) }
        FileHandle.standardError.write(Data("Ignoring non-absolute --event-log; using Library/Caches fixture log.\n".utf8))
    }
    return URL(fileURLWithPath: NSHomeDirectory())
        .appendingPathComponent("Library/Caches/tobkiri-computer-use/fixture-logs")
        .appendingPathComponent("drawing-\(ProcessInfo.processInfo.processIdentifier).jsonl")
}

struct InkStroke {
    var points: [NSPoint]
    let color: NSColor
    let width: CGFloat
}

final class DrawingCanvas: NSView {
    var strokes: [InkStroke] = []
    var ink = NSColor(calibratedRed: 0.13, green: 0.18, blue: 0.25, alpha: 1)
    var inkName = "Dark"
    var width: CGFloat = 4
    var changed: (() -> Void)?
    var eventWriter: AsyncJSONLWriter?
    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        setAccessibilityElement(true)
        setAccessibilityRole(.image)
        setAccessibilityLabel("Drawing canvas")
        setAccessibilityHelp("Draw by dragging inside this blank canvas. Choose an ink color above.")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) unavailable") }

    func point(_ event: NSEvent) -> NSPoint {
        let p = convert(event.locationInWindow, from: nil)
        return NSPoint(x: min(max(p.x, 2), bounds.width-2), y: min(max(p.y, 2), bounds.height-2))
    }
    func log(_ kind: String, _ p: NSPoint) {
        guard let eventWriter else { return }
        let value: [String: Any] = ["event": kind, "x": p.x, "y": p.y,
            "window_number": window?.windowNumber ?? -1, "stroke_count": strokes.count,
            "time": ProcessInfo.processInfo.systemUptime, "color": inkName,
            "app_active": NSApp.isActive, "window_key": window?.isKeyWindow ?? false]
        eventWriter.append(value)
    }
    override func mouseDown(with event: NSEvent) {
        let p = point(event)
        strokes.append(InkStroke(points: [p], color: ink, width: width))
        log("down", p); needsDisplay = true; changed?()
    }
    override func mouseDragged(with event: NSEvent) {
        guard !strokes.isEmpty else { return }
        let p = point(event)
        strokes[strokes.count-1].points.append(p)
        log("drag", p); needsDisplay = true
    }
    override func mouseUp(with event: NSEvent) {
        guard !strokes.isEmpty else { return }
        let p = point(event)
        strokes[strokes.count-1].points.append(p)
        log("up", p); needsDisplay = true; changed?()
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.white.setFill(); bounds.fill()
        NSColor(calibratedWhite: 0.82, alpha: 1).setStroke()
        NSBezierPath(rect: bounds.insetBy(dx: 0.5, dy: 0.5)).stroke()
        for stroke in strokes {
            guard let first = stroke.points.first else { continue }
            stroke.color.setStroke(); stroke.color.setFill()
            if stroke.points.count == 1 {
                NSBezierPath(ovalIn: NSRect(x: first.x-stroke.width/2, y: first.y-stroke.width/2,
                    width: stroke.width, height: stroke.width)).fill()
            } else {
                let path = NSBezierPath()
                path.lineWidth = stroke.width; path.lineCapStyle = .round; path.lineJoinStyle = .round
                path.move(to: first)
                for p in stroke.points.dropFirst() { path.line(to: p) }
                path.stroke()
            }
        }
    }
}

final class DrawingControls: NSObject {
    let canvas = DrawingCanvas(frame: NSRect(x: 28, y: 82, width: 804, height: 432))
    let status = NSTextField(labelWithString: "Strokes: 0 · Ink: Dark")
    let caption = NSTextField(string: "")
    var pixelMode = false
    var pixels: [Int: NSColor] = [:]
    var pixelUndo: [(NSButton, NSColor?)] = []
    let palette: [(String, NSColor)] = [
        ("Dark", NSColor(calibratedRed: 0.13, green: 0.18, blue: 0.25, alpha: 1)),
        ("Blue", .systemBlue), ("Red", .systemRed), ("Green", .systemGreen), ("Gold", .systemOrange)]
    func refresh() {
        let log = canvas.eventWriter?.diagnostics().summary ?? "log disabled"
        status.stringValue = pixelMode
            ? "Painted cells: \(pixels.count) · Ink: \(canvas.inkName) · \(log)"
            : "Strokes: \(canvas.strokes.count) · Ink: \(canvas.inkName) · \(log)"
    }
    @objc func pixel(_ sender: NSButton) {
        pixelUndo.append((sender, pixels[sender.tag]))
        pixels[sender.tag] = canvas.ink
        sender.layer?.backgroundColor = canvas.ink.cgColor
        canvas.log("pixel", NSPoint(x: sender.frame.midX, y: sender.frame.midY))
        refresh()
    }
    @objc func color(_ sender: NSButton) {
        let chosen = palette[sender.tag]
        canvas.inkName = chosen.0; canvas.ink = chosen.1; refresh()
    }
    @objc func undo() {
        if pixelMode {
            if let (button, previous) = pixelUndo.popLast() {
                pixels[button.tag] = previous
                button.layer?.backgroundColor = (previous ?? .white).cgColor
                refresh()
            }
            return
        }
        if !canvas.strokes.isEmpty { canvas.strokes.removeLast(); canvas.needsDisplay = true; refresh() }
    }
    @objc func clear() {
        canvas.strokes.removeAll(); canvas.needsDisplay = true
        pixels.removeAll(); pixelUndo.removeAll()
        for case let button as NSButton in canvas.subviews { button.layer?.backgroundColor = NSColor.white.cgColor }
        refresh()
    }
}

final class Controls: NSObject {
    var count = 0
    let status = NSTextField(labelWithString: "Count: 0")
    let name = NSTextField(string: "")
    let saved = NSTextField(labelWithString: "Ready")
    @objc func increment() { count += 1; status.stringValue = "Count: \(count)" }
    @objc func apply() { saved.stringValue = "Saved: \(name.stringValue)" }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
var fixtureLoggers: [AsyncJSONLWriter] = []
final class FixtureDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        fixtureLoggers.forEach { $0.close() }
    }
}
let delegate = FixtureDelegate()
app.delegate = delegate
var controls: [Controls] = []
var windows: [NSWindow] = []
let single = CommandLine.arguments.contains("--single") || Bundle.main.object(forInfoDictionaryKey: "TobkiriSingleWindow") as? Bool == true
let drawing = CommandLine.arguments.contains("--drawing") || Bundle.main.object(forInfoDictionaryKey: "TobkiriDrawingMode") as? Bool == true
let labels = drawing ? [] : (single ? ["A"] : ["A", "B"])
for (i, label) in labels.enumerated() {
    let c = Controls()
    let w = NSWindow(contentRect: NSRect(x: 80 + i * 510, y: 210, width: 480, height: 340),
                     styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
    w.title = "Tobkiri Fixture \(label)"
    w.isReleasedWhenClosed = false
    let heading = NSTextField(labelWithString: "Computer Use Test \(label)")
    heading.font = .boldSystemFont(ofSize: 22)
    heading.frame = NSRect(x: 30, y: 270, width: 410, height: 32)
    let button = NSButton(title: "Increment", target: c, action: #selector(Controls.increment))
    button.frame = NSRect(x: 30, y: 215, width: 150, height: 36)
    c.status.frame = NSRect(x: 210, y: 221, width: 200, height: 24)
    c.name.frame = NSRect(x: 30, y: 150, width: 260, height: 30)
    c.name.placeholderString = "Name"
    c.name.setAccessibilityLabel("Name")
    let save = NSButton(title: "Apply", target: c, action: #selector(Controls.apply))
    save.frame = NSRect(x: 310, y: 146, width: 125, height: 36)
    c.saved.frame = NSRect(x: 30, y: 95, width: 410, height: 28)
    let hint = NSTextField(labelWithString: "Local fixture • no network or user documents")
    hint.frame = NSRect(x: 30, y: 35, width: 420, height: 24)
    for view in [heading, button, c.status, c.name, save, c.saved, hint] { w.contentView!.addSubview(view) }
    w.orderFrontRegardless()
    controls.append(c); windows.append(w)
}
var drawingControls: DrawingControls?
if drawing {
    let c = DrawingControls()
    c.pixelMode = Bundle.main.object(forInfoDictionaryKey: "TobkiriPixelMode") as? Bool == true
    drawingControls = c
    let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1400, height: 900)
    let w = NSWindow(contentRect: NSRect(x: screen.midX-430, y: screen.midY-310, width: 860, height: 620),
                     styleMask: [.titled, .closable], backing: .buffered, defer: false)
    // A disposable work surface should be usable while the user stays in a
    // fullscreen app. Never activate the fixture or move the user's Space.
    w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    // Cua inventories normal (layer-0) windows and validates AXWindows membership.
    w.level = .normal
    w.title = c.pixelMode ? "Tobkiri Pixel Fixture" : "Tobkiri Drawing Fixture"
    w.isReleasedWhenClosed = false
    let heading = NSTextField(labelWithString: "A blank canvas for your agent")
    heading.font = .boldSystemFont(ofSize: 22)
    heading.frame = NSRect(x: 28, y: 565, width: 700, height: 32)
    w.contentView!.addSubview(heading)
    for (i, item) in c.palette.enumerated() {
        let button = NSButton(title: "Ink \(item.0)", target: c, action: #selector(DrawingControls.color(_:)))
        button.tag = i
        button.frame = NSRect(x: 24 + i*100, y: 521, width: 96, height: 34)
        w.contentView!.addSubview(button)
    }
    let undo = NSButton(title: "Undo stroke", target: c, action: #selector(DrawingControls.undo))
    undo.frame = NSRect(x: 563, y: 521, width: 125, height: 34)
    let clear = NSButton(title: "Clear canvas", target: c, action: #selector(DrawingControls.clear))
    clear.frame = NSRect(x: 700, y: 521, width: 130, height: 34)
    c.status.frame = NSRect(x: 28, y: 45, width: 360, height: 24)
    c.caption.frame = NSRect(x: 390, y: 43, width: 442, height: 28)
    c.caption.placeholderString = "Give your drawing a title"
    c.caption.setAccessibilityLabel("Drawing title")
    c.canvas.changed = { [weak c] in c?.refresh() }
    let writer = AsyncJSONLWriter(url: drawingEventLogURL())
    c.canvas.eventWriter = writer
    fixtureLoggers.append(writer)
    Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak c] _ in c?.refresh() }
    if c.pixelMode {
        c.canvas.setAccessibilityRole(.group)
        c.canvas.setAccessibilityLabel("Pixel canvas: 24 columns, 16 rows")
        c.canvas.setAccessibilityHelp("Choose an ink color, then click individual cells to paint. Row 1 is at the top.")
        let cellWidth = c.canvas.bounds.width / 24
        let cellHeight = c.canvas.bounds.height / 16
        for row in 0..<16 {
            for column in 0..<24 {
                let button = NSButton(title: "", target: c, action: #selector(DrawingControls.pixel(_:)))
                button.tag = row*24 + column
                button.setAccessibilityLabel("Pixel row \(row+1) column \(column+1)")
                button.isBordered = false
                button.wantsLayer = true
                button.layer?.backgroundColor = NSColor.white.cgColor
                button.layer?.borderWidth = 0.5
                button.layer?.borderColor = NSColor(calibratedWhite: 0.9, alpha: 1).cgColor
                button.frame = NSRect(x: CGFloat(column)*cellWidth, y: CGFloat(row)*cellHeight, width: cellWidth, height: cellHeight)
                c.canvas.addSubview(button)
            }
        }
        c.refresh()
    }
    for view in [c.canvas, undo, clear, c.status, c.caption] { w.contentView!.addSubview(view) }
    w.orderFrontRegardless()
    windows.append(w)
}
app.run()

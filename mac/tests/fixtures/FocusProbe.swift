// Read-only focus evidence. Never records titles, text, clipboard or keystrokes.
import Cocoa
import ApplicationServices

func focus() -> [String: Any] {
    guard let running = NSWorkspace.shared.frontmostApplication else { return ["pid": -1] }
    var result: [String: Any] = ["pid": Int(running.processIdentifier)]
    let app = AXUIElementCreateApplication(running.processIdentifier)
    var element: CFTypeRef?
    let error = AXUIElementCopyAttributeValue(app, kAXFocusedUIElementAttribute as CFString, &element)
    result["focused_element_status"] = error.rawValue
    if error == .success, let element = element {
        let target = element as! AXUIElement
        var role: CFTypeRef?
        if AXUIElementCopyAttributeValue(target, kAXRoleAttribute as CFString, &role) == .success {
            result["role"] = role as? String
        }
        for (key, attr) in [("position", kAXPositionAttribute), ("size", kAXSizeAttribute)] {
            var value: CFTypeRef?
            if AXUIElementCopyAttributeValue(target, attr as CFString, &value) == .success, let value = value {
                let ax = value as! AXValue
                if key == "position" {
                    var point = CGPoint.zero
                    if AXValueGetValue(ax, .cgPoint, &point) { result[key] = [point.x, point.y] }
                } else {
                    var size = CGSize.zero
                    if AXValueGetValue(ax, .cgSize, &size) { result[key] = [size.width, size.height] }
                }
            }
        }
    }
    return result
}

let duration = Double(CommandLine.arguments.dropFirst().first ?? "0") ?? 0
let deadline = Date().addingTimeInterval(duration)
repeat {
    if let data = try? JSONSerialization.data(withJSONObject: focus(), options: [.sortedKeys]),
       let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
    if duration > 0 { Thread.sleep(forTimeInterval: 0.05) }
} while Date() < deadline

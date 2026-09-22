// Read-only diagnostic for a disposable Tobkiri fixture, never an input route.
// Run only from a live-test actor. Its TCC attribution differs from the daemon.
import Cocoa
import ApplicationServices

@_silgen_name("_AXUIElementGetWindow")
func exactWindowID(_ element: AXUIElement, _ window: UnsafeMutablePointer<CGWindowID>) -> AXError

func read(_ element: AXUIElement, _ attribute: String) -> (AXError, CFTypeRef?) {
    var value: CFTypeRef?
    let error = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
    return (error, value)
}

guard CommandLine.arguments.count == 3,
      let pid = Int32(CommandLine.arguments[1]), pid > 0,
      let targetWindow = UInt32(CommandLine.arguments[2]),
      let running = NSRunningApplication(processIdentifier: pid),
      let name = running.localizedName,
      name.hasPrefix("Tobkiri"), name.hasSuffix("Fixture") else {
    fputs("Usage: ax-window-reference-probe FIXTURE_PID WINDOW_ID\n", stderr)
    exit(2)
}

let app = AXUIElementCreateApplication(pid)
// This configures only this client's synchronous read timeout.
let timeoutError = AXUIElementSetMessagingTimeout(app, 2)
var attributes: [[String: Any]] = []
for attribute in ["AXWindows", "AXChildren", "AXFocusedWindow", "AXMainWindow"] {
    let (error, value) = read(app, attribute)
    var elements: [AXUIElement] = []
    if let value = value {
        if CFGetTypeID(value) == AXUIElementGetTypeID() {
            elements = [unsafeBitCast(value, to: AXUIElement.self)]
        } else if let array = value as? [AnyObject] {
            elements = array.compactMap { item in
                guard CFGetTypeID(item) == AXUIElementGetTypeID() else { return nil }
                return unsafeBitCast(item, to: AXUIElement.self)
            }
        }
    }
    let refs: [[String: Any]] = elements.prefix(128).map { element in
        var owner: pid_t = 0
        let ownerError = AXUIElementGetPid(element, &owner)
        var window: CGWindowID = 0
        let windowError = exactWindowID(element, &window)
        let (roleError, role) = read(element, "AXRole")
        return ["pid": owner, "pid_error": ownerError.rawValue,
                "window_id": window, "window_id_error": windowError.rawValue,
                "role": (role as? String) ?? "", "role_error": roleError.rawValue,
                "exact_match": ownerError == .success && windowError == .success
                    && owner == pid && window == targetWindow]
    }
    attributes.append(["attribute": attribute, "error": error.rawValue,
                       "returned_count": elements.count, "references": refs])
}
let report: [String: Any] = [
    "timestamp": ISO8601DateFormatter().string(from: Date()),
    "target_pid": pid, "target_window_id": targetWindow, "fixture_app": name,
    "probe_pid": ProcessInfo.processInfo.processIdentifier,
    "accessibility_trusted": AXIsProcessTrusted(),
    "read_timeout_error": timeoutError.rawValue,
    "attribution_note": "Standalone read-only helper; not the candidate daemon's TCC identity",
    "input_sent": false, "attributes": attributes
]
let bytes = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(bytes)
FileHandle.standardOutput.write(Data([10]))

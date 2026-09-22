// In-memory NSEvent getter probe. It never creates an NSApplication or posts an event.
import Cocoa

let arguments = Array(CommandLine.arguments.dropFirst())
guard arguments.count == 1,
      let event = NSEvent.mouseEvent(with: .leftMouseDown,
                                     location: NSPoint(x: 11, y: 13),
                                     modifierFlags: [], timestamp: 0,
                                     windowNumber: 0, context: nil,
                                     eventNumber: 0, clickCount: 1, pressure: 1) else {
    FileHandle.standardError.write(Data("usage: PointerEventGetterReproducer <getter>\n".utf8))
    exit(64)
}

let value: Any
switch arguments[0] {
case "button_number": value = event.buttonNumber
case "click_count": value = event.clickCount
case "scrolling_delta_x": value = event.scrollingDeltaX
case "scrolling_delta_y": value = event.scrollingDeltaY
case "precise_scroll": value = event.hasPreciseScrollingDeltas
case "phase": value = event.phase.rawValue
default:
    FileHandle.standardError.write(Data("unknown getter: \(arguments[0])\n".utf8))
    exit(64)
}

let row: [String: Any] = ["getter": arguments[0], "event_type": event.type.rawValue, "value": value]
let data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data([10]))

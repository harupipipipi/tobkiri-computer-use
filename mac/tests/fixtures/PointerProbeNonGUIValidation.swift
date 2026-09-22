// Compiled with PointerProbe.swift -D POINTER_PROBE_VALIDATION; no app or window is created.
import Cocoa

@main
struct PointerProbeNonGUIValidation {
    static func require(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fatalError(message) }
    }

    static func main() throws {
        guard let mouse = NSEvent.mouseEvent(with: .leftMouseDown,
                                             location: NSPoint(x: 17, y: 19),
                                             modifierFlags: [], timestamp: 0,
                                             windowNumber: 0, context: nil,
                                             eventNumber: 0, clickCount: 1, pressure: 1) else {
            fatalError("could not create in-memory mouse event")
        }

        let fields = nativeEventFields(mouse)
        require(fields["button_number"] as? Int == 0, "mouse button was not retained")
        require(fields["click_count"] as? Int == 1, "mouse click count was not retained")
        require(fields["scrolling_delta_x"] == nil, "mouse log queried scroll delta")
        require(fields["scrolling_delta_y"] == nil, "mouse log queried scroll delta")
        require(fields["precise_scroll"] == nil, "mouse log queried precise scroll")
        require(fields["phase"] == nil, "mouse log queried scroll phase")
        let mouseDelta = counterDeltas(for: mouse)
        require(mouseDelta.x == 0 && mouseDelta.y == 0, "mouse counter queried scroll delta")

        guard let scrollCG = CGEvent(scrollWheelEvent2Source: nil, units: .pixel,
                                     wheelCount: 2, wheel1: 9, wheel2: -3, wheel3: 0),
              let scroll = NSEvent(cgEvent: scrollCG) else {
            fatalError("could not create in-memory scroll event")
        }
        require(scroll.type == .scrollWheel, "in-memory event was not scrollWheel")
        let scrollFields = nativeEventFields(scroll)
        require(scrollFields["scrolling_delta_x"] != nil, "scroll log lost x delta")
        require(scrollFields["scrolling_delta_y"] != nil, "scroll log lost y delta")
        require(scrollFields["precise_scroll"] != nil, "scroll log lost precision")
        require(scrollFields["phase"] != nil, "scroll log lost phase")
        require(scrollFields["button_number"] == nil, "scroll log queried button")
        require(scrollFields["click_count"] == nil, "scroll log queried click count")
        let scrollDelta = counterDeltas(for: scroll)

        var counters = ProbeCounters()
        counters.add("left_down", deltaX: mouseDelta.x, deltaY: mouseDelta.y)
        counters.add("wheel", deltaX: scrollDelta.x, deltaY: scrollDelta.y)
        let counts = counters.json()
        require(counts["left_down"] as? Int == 1, "left counter changed")
        require(counts["wheel"] as? Int == 1, "wheel counter changed")
        require(counts["wheel_delta_x"] as? Double == scrollDelta.x, "wheel x delta changed")
        require(counts["wheel_delta_y"] as? Double == scrollDelta.y, "wheel y delta changed")

        let result: [String: Any] = ["validation": "typed_fields_and_counters",
                                     "mouse_fields": fields, "scroll_fields": scrollFields, "counts": counts]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    }
}

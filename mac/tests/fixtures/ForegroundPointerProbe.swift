// Read-only measurement for fixture trials. No activation or input posting.
// Records only process IDs and pointer coordinates, never UI text or keys.
import Cocoa
import CoreGraphics

func usageError(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\nusage: ForegroundPointerProbe <seconds>\n" +
                                        "<seconds> must be one finite number from 0 through 120.\n").utf8))
    exit(64)
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard arguments.count == 1 else {
    usageError("expected exactly one bare duration argument")
}
guard let seconds = Double(arguments[0]), seconds.isFinite, (0...120).contains(seconds) else {
    usageError("duration must be a finite number from 0 through 120 seconds")
}
let deadline = ProcessInfo.processInfo.systemUptime + seconds
repeat {
    let point = CGEvent(source: nil)?.location
    let sample: [String: Any] = [
        "uptime": ProcessInfo.processInfo.systemUptime,
        "frontmost_pid": NSWorkspace.shared.frontmostApplication?.processIdentifier ?? -1,
        "pointer": point.map { [$0.x, $0.y] } as Any? ?? NSNull(),
    ]
    if let data = try? JSONSerialization.data(withJSONObject: sample, options: [.sortedKeys]),
       let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
    if seconds > 0 { Thread.sleep(forTimeInterval: 0.02) }
} while ProcessInfo.processInfo.systemUptime < deadline

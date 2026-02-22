import Foundation
import SQLite3

// MARK: - Data types

struct ServerInfo: Identifiable {
    let id = UUID()
    let port: String
    let name: String
    let color: MonitorColor
}

struct ProcessEntry: Identifiable {
    let id = UUID()
    let name: String
    let color: MonitorColor
    let cpu: Double
    let mem: Double
}

struct OllamaModel: Identifiable {
    let id = UUID()
    let name: String
    let sizeGB: Double
}

enum OllamaStatus { case up, idle, down }

enum MonitorColor {
    case green, teal, blue, sky, orange, yellow, magenta, lavender, dim
}

// MARK: - Thread-safe DB reader

final class DBReader: @unchecked Sendable {
    private var db: OpaquePointer?

    private static let requiredFields = [
        "visual_weight", "energy_direction", "archetype", "color_temp",
        "cartoon_style", "story_silly", "story_poetic", "story_surrealist",
        "story_noir", "story_romantic", "print_worthy",
        "setting", "time_of_day", "vibes", "faces_count",
    ]
    private static let intFields: Set<String> = ["visual_weight", "print_worthy", "faces_count"]

    static let gemmaWhere: String = requiredFields.map { f in
        intFields.contains(f) ? "\(f) IS NOT NULL" : "(\(f) IS NOT NULL AND \(f) != '')"
    }.joined(separator: " AND ")

    private static let isoFmt: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSSZZZZZ"
        df.locale = Locale(identifier: "en_US_POSIX")
        return df
    }()
    private static let isoFmtShort: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd'T'HH:mm:ssZZZZZ"
        df.locale = Locale(identifier: "en_US_POSIX")
        return df
    }()

    init?(path: String) {
        var handle: OpaquePointer?
        guard sqlite3_open_v2(path, &handle,
                              SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK else {
            return nil
        }
        db = handle
        sqlite3_exec(db, "PRAGMA journal_mode=WAL", nil, nil, nil)
    }

    deinit { if let db { sqlite3_close(db) } }

    // MARK: Queries

    func gemmaDone() -> Int {
        queryInt("SELECT COUNT(*) FROM gemma_analysis WHERE \(Self.gemmaWhere)")
    }

    func gemmaRate() -> Double {
        guard let db else { return 0 }
        let sql = """
            SELECT processed_at FROM gemma_analysis
            WHERE \(Self.gemmaWhere)
            ORDER BY processed_at DESC LIMIT 20
            """
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return 0 }

        var timestamps: [Double] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let ptr = sqlite3_column_text(stmt, 0) else { continue }
            let s = String(cString: ptr).replacingOccurrences(of: "Z", with: "+00:00")
            if let d = Self.isoFmt.date(from: s) ?? Self.isoFmtShort.date(from: s) {
                timestamps.append(d.timeIntervalSince1970)
            }
        }
        guard timestamps.count >= 2 else { return 0 }
        let span = timestamps[0] - timestamps[timestamps.count - 1]
        return span > 0 ? Double(timestamps.count - 1) / span : 0
    }

    func gemmaLatest() -> (subject: String, mood: String)? {
        guard let db else { return nil }
        let sql = "SELECT subject, mood FROM gemma_analysis ORDER BY processed_at DESC LIMIT 1"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK,
              sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        let subject = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
        let mood = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
        return (subject, mood)
    }

    func dbStats() -> (images: Int, gemma: Int, gemini: Int, variants: Int) {
        (queryInt("SELECT COUNT(*) FROM images"),
         queryInt("SELECT COUNT(*) FROM gemma_analysis"),
         queryInt("SELECT COUNT(*) FROM gemini_analysis"),
         queryInt("SELECT COUNT(*) FROM ai_variants WHERE generation_status='success'"))
    }

    private func queryInt(_ sql: String) -> Int {
        guard let db else { return 0 }
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK,
              sqlite3_step(stmt) == SQLITE_ROW else { return 0 }
        return Int(sqlite3_column_int64(stmt, 0))
    }
}

// MARK: - System fetchers

enum Fetchers {

    static func scanServers() -> [ServerInfo] {
        let output = shell("/usr/sbin/lsof", ["-iTCP", "-sTCP:LISTEN", "-P", "-n"])
        var seen = Set<String>()
        var result: [ServerInfo] = []

        for line in output.split(separator: "\n").dropFirst() {
            let parts = line.split(separator: " ", maxSplits: 10, omittingEmptySubsequences: true)
            guard parts.count >= 9 else { continue }
            let name = String(parts[0])
            let addr = String(parts[8])
            guard let port = addr.split(separator: ":").last.map(String.init),
                  !seen.contains(port) else { continue }
            seen.insert(port)

            let entry: (String, MonitorColor)?
            switch (name.lowercased(), port) {
            case ("ollama", _):                   entry = ("Ollama", .green)
            case (_, "3000"):                     entry = ("Show srv", .blue)
            case (_, "8080"):                     entry = ("Dashboard", .blue)
            case (_, "5173"):                     entry = ("System vite", .sky)
            case (_, "5174"):                     entry = ("Show vite", .sky)
            default:                              entry = nil
            }
            if let (label, color) = entry {
                result.append(ServerInfo(port: port, name: label, color: color))
            }
        }
        return result.sorted { $0.port < $1.port }
    }

    static func scanProcesses() -> [ProcessEntry] {
        let output = shell("/bin/ps", ["aux"])
        var result: [ProcessEntry] = []

        for line in output.split(separator: "\n").dropFirst() {
            let parts = line.split(separator: " ", maxSplits: 10, omittingEmptySubsequences: true)
            guard parts.count >= 11 else { continue }
            let cpu = Double(parts[2]) ?? 0
            let mem = Double(parts[3]) ?? 0
            let cmd = String(parts[10])

            guard cmd.contains("MADphotos") || cmd.lowercased().contains("ollama") else { continue }
            guard !cmd.contains("grep"), !cmd.contains("monitor.py"), !cmd.contains("See") else { continue }

            let (name, color) = categorize(cmd)
            guard name != "Ollama serve", name != "Gemma monitor" else { continue }
            result.append(ProcessEntry(name: name, color: color, cpu: cpu, mem: mem))
        }
        return result
    }

    static func checkOllama() async -> ([OllamaModel], OllamaStatus) {
        guard let url = URL(string: "http://localhost:11434/api/ps") else { return ([], .down) }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let models = json["models"] as? [[String: Any]] else { return ([], .idle) }
            if models.isEmpty { return ([], .idle) }
            return (models.map { m in
                OllamaModel(
                    name: m["name"] as? String ?? "?",
                    sizeGB: Double(m["size_vram"] as? Int ?? 0) / 1e9
                )
            }, .up)
        } catch {
            return ([], .down)
        }
    }

    private static func categorize(_ cmd: String) -> (String, MonitorColor) {
        let cl = cmd.lowercased()
        if cl.contains("run_gemma_forever")  { return ("Gemma forever", .teal) }
        if cl.contains("run_gemma_analysis") { return ("Gemma analysis", .teal) }
        if cl.contains("gemma_monitor")      { return ("Gemma monitor", .dim) }
        if cl.contains("serve_show")         { return ("Show server", .blue) }
        if cl.contains("dashboard.py")       { return ("Dashboard", .blue) }
        if cl.contains("imagen.py")          { return ("Imagen", .magenta) }
        if cl.contains("firestore_sync")     { return ("Firestore sync", .teal) }
        if cl.contains("export_gallery")     { return ("Export", .teal) }
        if cl.contains("signals") || cl.contains("pipeline") { return ("Signals", .yellow) }
        if cl.contains("render.py") || cl.contains("enhance") { return ("Render", .orange) }
        if cl.contains("vite") && cl.contains("system") { return ("System vite", .sky) }
        if cl.contains("vite") && cl.contains("show")   { return ("Show vite", .sky) }
        if cl.contains("vite")               { return ("Vite", .sky) }
        if cl.contains("ollama") && cl.contains("runner") { return ("Ollama runner", .green) }
        if cl.contains("ollama") && cl.contains("serve")  { return ("Ollama serve", .green) }
        if cl.contains("server.py")          { return ("System srv", .blue) }
        return ("Process", .dim)
    }

    private static func shell(_ cmd: String, _ args: [String]) -> String {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: cmd)
        task.arguments = args
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        do {
            try task.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            task.waitUntilExit()
            return String(data: data, encoding: .utf8) ?? ""
        } catch { return "" }
    }
}

// MARK: - Observable state

@MainActor
final class MonitorState: ObservableObject {
    @Published var servers: [ServerInfo] = []
    @Published var processes: [ProcessEntry] = []
    @Published var ollamaModels: [OllamaModel] = []
    @Published var ollamaStatus: OllamaStatus = .down

    @Published var gemmaTotal = 0
    @Published var gemmaDone = 0
    @Published var gemmaRate: Double = 0
    @Published var gemmaSubject = ""
    @Published var gemmaMood = ""
    @Published var gemmaSessionDelta = 0

    @Published var dbImages = 0
    @Published var dbGemma = 0
    @Published var dbGemini = 0
    @Published var dbVariants = 0

    @Published var uptime: TimeInterval = 0

    private let reader: DBReader?
    private var timer: Timer?
    private let startTime = Date()
    private var sessionStart = 0

    private static let home = FileManager.default.homeDirectoryForCurrentUser.path
    private static let dbPath = "\(home)/Github/MADphotos/images/mad_photos.db"
    private static let picksPath = "\(home)/Github/MADphotos/frontend/show/public/data/picks.json"

    init() {
        reader = DBReader(path: Self.dbPath)
    }

    func start() {
        loadTotal()
        sessionStart = reader?.gemmaDone() ?? 0
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.refresh() }
        }
    }

    func stop() { timer?.invalidate(); timer = nil }

    private func loadTotal() {
        guard let data = FileManager.default.contents(atPath: Self.picksPath),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        var uuids = Set<String>()
        for key in ["portrait", "landscape"] {
            if let arr = json[key] as? [String] {
                for u in arr where !u.contains("_") { uuids.insert(u) }
            }
        }
        gemmaTotal = uuids.count
    }

    private func refresh() {
        uptime = Date().timeIntervalSince(startTime)

        let reader = self.reader
        Task.detached(priority: .utility) {
            let servers = Fetchers.scanServers()
            let processes = Fetchers.scanProcesses()
            let (models, status) = await Fetchers.checkOllama()

            let done = reader?.gemmaDone() ?? 0
            let rate = reader?.gemmaRate() ?? 0
            let latest = reader?.gemmaLatest()
            let stats = reader?.dbStats()

            await MainActor.run { [weak self] in
                guard let self else { return }
                self.servers = servers
                self.processes = processes
                self.ollamaModels = models
                self.ollamaStatus = status
                self.gemmaDone = done
                self.gemmaSessionDelta = done - self.sessionStart
                self.gemmaRate = rate
                if let latest {
                    self.gemmaSubject = latest.subject
                    self.gemmaMood = latest.mood
                }
                self.dbImages = stats?.images ?? 0
                self.dbGemma = stats?.gemma ?? 0
                self.dbGemini = stats?.gemini ?? 0
                self.dbVariants = stats?.variants ?? 0
            }
        }
    }
}

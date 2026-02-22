import SwiftUI

struct MonitorView: View {
    @EnvironmentObject var windowState: WindowState
    @StateObject private var state = MonitorState()
    @State private var spinIndex = 0

    private static let spinChars = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    private let spinTimer = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            header
            divider
            services
            divider
            gemma
            divider
            footer
        }
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
        .onAppear { state.start() }
        .onDisappear { state.stop() }
        .onReceive(spinTimer) { _ in
            spinIndex = (spinIndex + 1) % Self.spinChars.count
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 8) {
            Text(Self.spinChars[spinIndex])
                .font(.system(size: 13))
                .foregroundStyle(.green)
            Text("MADphotos")
                .font(.system(size: 14, weight: .bold))
            Spacer()
            Text(formatUptime(state.uptime))
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.secondary)
            Button(action: { windowState.toggleFloat() }) {
                Image(systemName: windowState.isFloating ? "pin.fill" : "pin")
                    .font(.system(size: 10))
                    .foregroundStyle(windowState.isFloating ? .white : .secondary)
            }
            .buttonStyle(.plain)
            .help(windowState.isFloating ? "Unpin from top" : "Pin on top")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }

    // MARK: - Services (two columns)

    private var services: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left — servers + Ollama
            VStack(alignment: .leading, spacing: 4) {
                ForEach(state.servers) { s in
                    HStack(spacing: 6) {
                        dot(s.color)
                        Text(":\(s.port)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(width: 44, alignment: .leading)
                        Text(s.name)
                            .font(.system(size: 11, weight: .medium))
                    }
                }
                ForEach(state.ollamaModels) { m in
                    HStack(spacing: 6) {
                        dot(.green)
                        Text(truncate(m.name, 22))
                            .font(.system(size: 11, weight: .medium))
                        Text("\(Int(m.sizeGB))GB")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                if state.ollamaStatus == .idle {
                    HStack(spacing: 6) {
                        dot(.yellow)
                        Text("Ollama")
                            .font(.system(size: 11, weight: .medium))
                        Text("idle")
                            .font(.system(size: 10))
                            .foregroundStyle(.yellow)
                    }
                } else if state.ollamaStatus == .down {
                    HStack(spacing: 6) {
                        dot(.dim)
                        Text("Ollama")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(.secondary)
                        Text("down")
                            .font(.system(size: 10))
                            .foregroundStyle(.red)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Vertical separator
            Rectangle()
                .fill(.quaternary)
                .frame(width: 1)
                .padding(.vertical, 2)

            // Right — processes
            VStack(alignment: .leading, spacing: 4) {
                ForEach(state.processes) { p in
                    HStack(spacing: 6) {
                        dot(p.color)
                        Text(p.name)
                            .font(.system(size: 11, weight: .medium))
                            .frame(width: 106, alignment: .leading)
                        Text(p.cpu >= 0.5 ? "\(Int(p.cpu))%" : "–")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(width: 28, alignment: .trailing)
                        Text(p.mem >= 0.1 ? String(format: "%.1f%%", p.mem) : "–")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(width: 38, alignment: .trailing)
                    }
                }
                if state.processes.isEmpty {
                    Text("no processes")
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Gemma progress

    private var gemma: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Title + counts
            HStack(spacing: 0) {
                Text("Gemma")
                    .font(.system(size: 12, weight: .bold))
                Spacer()
                if state.gemmaTotal > 0 {
                    Text(String(format: "%.1f%%", gemmaPct))
                        .font(.system(size: 12, weight: .bold, design: .monospaced))
                    Text("  ")
                    Text("\(formatted(state.gemmaDone))")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.green)
                    Text(" / \(formatted(state.gemmaTotal))")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }

            if state.gemmaTotal > 0 {
                // Progress bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(.white.opacity(0.06))
                        RoundedRectangle(cornerRadius: 2)
                            .fill(barGradient)
                            .frame(width: max(0, geo.size.width * gemmaPct / 100))
                            .animation(.easeInOut(duration: 0.4), value: state.gemmaDone)
                    }
                }
                .frame(height: 4)

                // Rate + ETA
                if state.gemmaRate > 0 {
                    rateRow
                } else if state.gemmaDone >= state.gemmaTotal {
                    Text("Complete!")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.green)
                } else {
                    HStack(spacing: 0) {
                        Text("\(formatted(state.gemmaTotal - state.gemmaDone))")
                            .foregroundStyle(.yellow)
                        Text(" left — estimating…")
                            .foregroundStyle(.secondary)
                    }
                    .font(.system(size: 10, design: .monospaced))
                }

                // Latest image
                if !state.gemmaSubject.isEmpty {
                    HStack(spacing: 0) {
                        Text(truncate(state.gemmaSubject, 40))
                            .foregroundStyle(.secondary)
                        if !state.gemmaMood.isEmpty {
                            Text("  ")
                            Text(truncate(state.gemmaMood, 24))
                                .foregroundStyle(MonitorColor.lavender.swiftUI)
                        }
                    }
                    .font(.system(size: 10, design: .monospaced))
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var rateRow: some View {
        let remaining = state.gemmaTotal - state.gemmaDone
        let eta = state.gemmaRate > 0 ? Double(remaining) / state.gemmaRate : 0
        let secPerImg = 1.0 / state.gemmaRate
        let perMin = state.gemmaRate * 60

        HStack(spacing: 0) {
            Text("\(formatted(remaining))")
                .foregroundStyle(.yellow)
            Text(" left  ")
                .foregroundStyle(.secondary)
            Text("\(Int(secPerImg))s")
                .foregroundStyle(MonitorColor.teal.swiftUI)
            Text("/img  ")
                .foregroundStyle(.secondary)
            Text(String(format: "%.1f", perMin))
                .foregroundStyle(MonitorColor.teal.swiftUI)
            Text("/min  ")
                .foregroundStyle(.secondary)
            Text(formatETA(eta))
                .foregroundStyle(.cyan)
            if state.gemmaSessionDelta > 0 {
                Text("  +\(state.gemmaSessionDelta)")
                    .foregroundStyle(.secondary)
            }
        }
        .font(.system(size: 10, design: .monospaced))
    }

    // MARK: - Footer

    private var footer: some View {
        HStack(spacing: 0) {
            Text("DB")
                .foregroundStyle(.secondary)
            statPill(state.dbImages, "imgs")
            statPill(state.dbGemma, "gemma")
            statPill(state.dbGemini, "gemini")
            statPill(state.dbVariants, "variants")
            Spacer()
        }
        .font(.system(size: 10, design: .monospaced))
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Shared components

    private var divider: some View {
        Rectangle()
            .fill(.quaternary)
            .frame(height: 1)
            .padding(.horizontal, 8)
    }

    private func dot(_ color: MonitorColor) -> some View {
        Circle()
            .fill(color.swiftUI)
            .frame(width: 6, height: 6)
    }

    private func statPill(_ value: Int, _ label: String) -> some View {
        Group {
            Text("  \(formatted(value))").foregroundStyle(.white)
            Text(" \(label)").foregroundStyle(.secondary)
        }
    }

    // MARK: - Computed

    private var gemmaPct: Double {
        guard state.gemmaTotal > 0 else { return 0 }
        return Double(state.gemmaDone) * 100.0 / Double(state.gemmaTotal)
    }

    private var barGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 0, green: 0.37, blue: 0.53),
                Color(red: 0, green: 0.53, blue: 0.53),
                Color(red: 0, green: 0.69, blue: 0.53),
                Color(red: 0, green: 0.84, blue: 0.69),
                Color(red: 0.37, green: 1, blue: 0.69),
                Color(red: 0.53, green: 1, blue: 0.69),
            ],
            startPoint: .leading,
            endPoint: .trailing
        )
    }

    // MARK: - Formatters

    private func formatUptime(_ t: TimeInterval) -> String {
        let s = Int(t)
        return String(format: "%02d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60)
    }

    private func formatETA(_ seconds: Double) -> String {
        guard seconds > 0 else { return "done" }
        let h = Int(seconds) / 3600
        let m = (Int(seconds) % 3600) / 60
        let fin = Date().addingTimeInterval(seconds)
        let fmt = DateFormatter()
        fmt.dateFormat = fin.timeIntervalSinceNow > 86400 ? "HH:mm 'tmrw'" : "HH:mm"
        let durStr = h > 0 ? "\(h)h\(String(format: "%02d", m))m" : "\(m)m"
        return "\(durStr) → \(fmt.string(from: fin))"
    }

    private func formatted(_ n: Int) -> String {
        let fmt = NumberFormatter()
        fmt.numberStyle = .decimal
        return fmt.string(from: NSNumber(value: n)) ?? "\(n)"
    }

    private func truncate(_ s: String, _ n: Int) -> String {
        s.count > n ? String(s.prefix(n - 1)) + "…" : s
    }
}

// MARK: - Color mapping

extension MonitorColor {
    var swiftUI: Color {
        switch self {
        case .green:    .green
        case .teal:     Color(red: 0, green: 0.84, blue: 0.69)
        case .blue:     .blue
        case .sky:      Color(red: 0.53, green: 0.84, blue: 1)
        case .orange:   .orange
        case .yellow:   .yellow
        case .magenta:  .purple
        case .lavender: Color(red: 0.84, green: 0.69, blue: 1)
        case .dim:      .gray
        }
    }
}

import SwiftUI

@main
struct SeeApp: App {
    @StateObject private var windowState = WindowState()

    var body: some Scene {
        WindowGroup {
            MonitorView()
                .environmentObject(windowState)
                .frame(width: 480)
                .preferredColorScheme(.dark)
                .background(WindowConfig(windowState: windowState))
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
    }
}

// MARK: - Window state (shared so the view can toggle float)

final class WindowState: ObservableObject {
    @Published var isFloating = true
    weak var window: NSWindow?

    func toggleFloat() {
        isFloating.toggle()
        window?.level = isFloating ? .floating : .normal
    }
}

// MARK: - Window configuration

private struct WindowConfig: NSViewRepresentable {
    @ObservedObject var windowState: WindowState

    final class Coordinator: NSObject {
        var configured = false
    }

    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> NSView { NSView() }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard !context.coordinator.configured, let w = nsView.window else { return }
        context.coordinator.configured = true
        w.isMovableByWindowBackground = true
        w.level = .floating
        w.collectionBehavior.insert(.canJoinAllSpaces)
        windowState.window = w
    }
}

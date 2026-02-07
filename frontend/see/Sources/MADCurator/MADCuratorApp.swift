import SwiftUI
import AppKit

// MADCurator — Native macOS curation interface for MADphotos
// Reads from mad_photos.db, displays thumbnails, filters by all Gemini tags

@main
struct MADCuratorApp: App {
    static let basePath = "/Users/laeh/Pictures/MADphotos"
    @StateObject private var store = PhotoStore(basePath: MADCuratorApp.basePath)

    var body: some Scene {
        WindowGroup("MADCurator") {
            ContentView()
                .environmentObject(store)
                .frame(minWidth: 1100, minHeight: 700)
        }
        .windowToolbarStyle(.unified(showsTitle: true))
        .defaultSize(width: 1400, height: 900)
        .commands {
            CommandGroup(replacing: .newItem) {}

            // Sidebar toggle
            CommandGroup(after: .sidebar) {
                Button("Toggle Sidebar") {
                    NSApp.keyWindow?.contentViewController?.tryToPerform(
                        #selector(NSSplitViewController.toggleSidebar(_:)), with: nil)
                }
                .keyboardShortcut("s", modifiers: [.command, .option])
            }

            CommandMenu("Curate") {
                Button("Keep") { store.keepCurrent() }
                    .keyboardShortcut("k", modifiers: [])
                Button("Reject") { store.rejectCurrent() }
                    .keyboardShortcut("r", modifiers: [])
                Divider()
                Button("Next") { store.moveToNext() }
                    .keyboardShortcut(.rightArrow, modifiers: [])
                Button("Previous") { store.moveToPrevious() }
                    .keyboardShortcut(.leftArrow, modifiers: [])
            }

            CommandMenu("View") {
                Button("Toggle Enhanced") { store.toggleEnhanced() }
                    .keyboardShortcut("e", modifiers: [])
                Button("Toggle Info Panel") { store.toggleInfoPanel() }
                    .keyboardShortcut("i", modifiers: [])
                Button("Toggle Fullscreen Preview") { store.toggleFullscreen() }
                    .keyboardShortcut(.space, modifiers: [])
                Divider()
                Button("Focus Search") {
                    // Send Cmd+F notification
                    NSApp.sendAction(#selector(NSResponder.becomeFirstResponder), to: nil, from: nil)
                }
                .keyboardShortcut("f", modifiers: [.command])
            }
        }
    }
}

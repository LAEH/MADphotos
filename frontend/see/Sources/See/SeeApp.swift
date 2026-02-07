import SwiftUI
import AppKit

class AppDelegate: NSObject, NSApplicationDelegate {
    weak var store: PhotoStore?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        // Set app icon
        let iconPath = SeeApp.basePath + "/frontend/see/See.icns"
        if let icon = NSImage(contentsOfFile: iconPath) {
            NSApp.applicationIconImage = icon
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        store?.savePreferences()
        store?.database.shutdown()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

@main
struct SeeApp: App {
    static let basePath = "/Users/laeh/Github/MADphotos"
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var store = PhotoStore(basePath: SeeApp.basePath)
    @AppStorage("appearance") private var appearance = 0  // 0=system, 1=light, 2=dark

    var body: some Scene {
        // Window 1: Collection navigator
        WindowGroup("Collection") {
            ContentView()
                .environmentObject(store)
                .preferredColorScheme(appearance == 1 ? .light : appearance == 2 ? .dark : nil)
                .onAppear { appDelegate.store = store }
        }
        .windowToolbarStyle(.unified)
        .defaultSize(width: 1100, height: 800)

        // Window 2: Image viewer
        Window("Viewer", id: "viewer") {
            ViewerWindow()
                .environmentObject(store)
                .preferredColorScheme(appearance == 1 ? .light : appearance == 2 ? .dark : nil)
        }
        .windowToolbarStyle(.unified)
        .defaultSize(width: 1000, height: 750)

        .commands {
            CommandGroup(replacing: .newItem) {}

            CommandGroup(after: .sidebar) {
                Button("Toggle Sidebar") {
                    NSApp.keyWindow?.contentViewController?.tryToPerform(
                        #selector(NSSplitViewController.toggleSidebar(_:)), with: nil)
                }
                .keyboardShortcut("s", modifiers: [.command, .option])
            }

            CommandMenu("Curate") {
                Button("Pick") { store.keepCurrent() }
                    .keyboardShortcut("p", modifiers: [])
                Button("Reject") { store.rejectCurrent() }
                    .keyboardShortcut("r", modifiers: [])
                Button("Unflag") { store.unflagCurrent() }
                    .keyboardShortcut("u", modifiers: [])
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
                Divider()
                Button("Focus Search") {
                    NSApp.sendAction(#selector(NSResponder.becomeFirstResponder), to: nil, from: nil)
                }
                .keyboardShortcut("f", modifiers: [.command])
                Divider()
                Menu("Appearance") {
                    Button("System") { appearance = 0 }
                    Button("Light") { appearance = 1 }
                    Button("Dark") { appearance = 2 }
                }
            }
        }
    }
}

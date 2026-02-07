// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "See",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "See",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        ),
    ]
)

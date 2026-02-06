// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MADCurator",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "MADCurator",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        ),
    ]
)

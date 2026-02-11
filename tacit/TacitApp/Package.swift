// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TacitApp",
    platforms: [
        .macOS(.v14)
    ],
    targets: [
        .executableTarget(
            name: "TacitApp",
            path: "Sources/TacitApp"
        )
    ]
)

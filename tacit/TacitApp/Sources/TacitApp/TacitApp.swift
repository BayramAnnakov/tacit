import SwiftUI

@main
struct TacitApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1200, height: 800)
        .commands {
            SidebarCommands()
            CommandGroup(replacing: .help) {
                Button("Tacit Help") {
                    NSWorkspace.shared.open(URL(string: "https://github.com/BayramAnnakov/tacit")!)
                }
            }
        }
    }
}

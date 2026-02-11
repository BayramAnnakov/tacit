import SwiftUI

struct MyDiscoveriesView: View {
    @State private var discoveries: [LocalDiscovery] = []
    @State private var showProposeSheet = false
    @State private var selectedDiscovery: LocalDiscovery?
    @State private var localPath = ""
    @State private var isScanning = false
    @Bindable var extractionVM: ExtractionViewModel

    var body: some View {
        Group {
            if discoveries.isEmpty {
                EmptyStateView(
                    icon: "lightbulb",
                    title: "No Local Discoveries",
                    message: "Enter a project path and scan your local Claude Code conversations to discover patterns."
                )
            } else {
                discoveryList
            }
        }
        .navigationTitle("My Discoveries")
        .toolbar {
            ToolbarItem(placement: .principal) {
                HStack(spacing: 6) {
                    Image(systemName: "folder")
                        .foregroundStyle(.secondary)
                    TextField("Project path...", text: $localPath)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 240)
                }
            }
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task {
                        isScanning = true
                        await extractionVM.startLocalExtraction(path: localPath)
                        isScanning = false
                    }
                } label: {
                    if isScanning {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label("Scan", systemImage: "magnifyingglass")
                    }
                }
                .disabled(localPath.isEmpty || isScanning)
                .help("Scan local project for patterns")
            }
        }
    }

    private var discoveryList: some View {
        List(discoveries) { discovery in
            VStack(alignment: .leading, spacing: 8) {
                Text(discovery.ruleText)
                    .font(.callout)
                    .lineLimit(3)

                HStack {
                    CategoryPill(category: discovery.category)
                    ConfidenceBadge(confidence: discovery.confidence)
                    Spacer()
                    Button {
                        selectedDiscovery = discovery
                        showProposeSheet = true
                    } label: {
                        Label("Propose to Team", systemImage: "arrow.up.doc")
                            .font(.caption)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }
            .padding(.vertical, 4)
        }
        .listStyle(.inset)
    }
}

struct LocalDiscovery: Identifiable, Hashable {
    let id = UUID()
    var ruleText: String
    var category: String
    var confidence: Double
    var sourceExcerpt: String
}

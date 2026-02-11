import SwiftUI

struct MyDiscoveriesView: View {
    @State private var discoveries: [LocalDiscovery] = []
    @State private var showProposeSheet = false
    @State private var selectedDiscovery: LocalDiscovery?
    @State private var localPath = ""
    @State private var isScanning = false
    @State private var proposedIds: Set<UUID> = []
    @Bindable var extractionVM: ExtractionViewModel
    @Bindable var proposalVM: ProposalViewModel

    var body: some View {
        Group {
            if isScanning {
                VStack(spacing: 16) {
                    ProgressView()
                        .controlSize(.large)
                    Text("Scanning local conversations...")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if discoveries.isEmpty {
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
                        await fetchDiscoveries()
                        isScanning = false
                    }
                } label: {
                    Label("Scan", systemImage: "magnifyingglass")
                }
                .disabled(localPath.isEmpty || isScanning)
                .help("Scan local project for patterns")
            }
        }
        .sheet(isPresented: $showProposeSheet) {
            if let discovery = selectedDiscovery {
                ProposeSheet(
                    discovery: discovery,
                    proposalVM: proposalVM,
                    onProposed: { proposedIds.insert(discovery.id) }
                )
            }
        }
    }

    private func fetchDiscoveries() async {
        do {
            let rules = try await BackendService.shared.listKnowledge()
            discoveries = rules
                .filter { $0.sourceType == .conversation }
                .map { rule in
                    LocalDiscovery(
                        ruleText: rule.ruleText,
                        category: rule.category,
                        confidence: rule.confidence,
                        sourceExcerpt: rule.sourceRef
                    )
                }
        } catch {
            discoveries = []
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
                    if proposedIds.contains(discovery.id) {
                        Label("Proposed", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(.green)
                    } else {
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
            }
            .padding(.vertical, 4)
        }
        .listStyle(.inset)
    }
}

struct ProposeSheet: View {
    let discovery: LocalDiscovery
    @Bindable var proposalVM: ProposalViewModel
    var onProposed: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var isSubmitting = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Propose to Team")
                .font(.headline)

            Text(discovery.ruleText)
                .font(.callout)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary)
                .clipShape(RoundedRectangle(cornerRadius: 8))

            HStack {
                CategoryPill(category: discovery.category)
                ConfidenceBadge(confidence: discovery.confidence)
            }

            HStack {
                Button("Cancel", role: .cancel) { dismiss() }
                Spacer()
                Button {
                    isSubmitting = true
                    Task {
                        await proposalVM.createProposal(
                            ruleText: discovery.ruleText,
                            category: discovery.category,
                            confidence: discovery.confidence,
                            sourceExcerpt: discovery.sourceExcerpt,
                            proposedBy: NSFullUserName()
                        )
                        onProposed()
                        isSubmitting = false
                        dismiss()
                    }
                } label: {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Label("Submit Proposal", systemImage: "arrow.up.doc")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSubmitting)
            }
        }
        .padding(24)
        .frame(width: 480)
    }
}

struct LocalDiscovery: Identifiable, Hashable {
    let id = UUID()
    var ruleText: String
    var category: String
    var confidence: Double
    var sourceExcerpt: String
}

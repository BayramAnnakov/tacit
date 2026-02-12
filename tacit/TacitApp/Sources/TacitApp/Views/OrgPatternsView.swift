import SwiftUI

struct OrgPatternsView: View {
    @State private var patterns: [OrgPattern] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading cross-repo patterns...")
            } else if let error = errorMessage {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if patterns.isEmpty {
                ContentUnavailableView(
                    "No Shared Patterns",
                    systemImage: "globe.americas",
                    description: Text("Add 2+ repositories and run extraction to discover shared conventions across your organization.")
                )
            } else {
                List(patterns) { pattern in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(pattern.ruleText)
                            .font(.body)

                        HStack(spacing: 8) {
                            Label(KnowledgeViewModel.displayName(for: pattern.category), systemImage: "tag.fill")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()

                            Text("Found in \(pattern.frequency) rule(s)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        HStack(spacing: 4) {
                            ForEach(pattern.repos, id: \.self) { repo in
                                Text(repo)
                                    .font(.caption2)
                                    .fontWeight(.medium)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.indigo.opacity(0.15))
                                    .foregroundStyle(.indigo)
                                    .clipShape(Capsule())
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
                .listStyle(.inset)
            }
        }
        .navigationTitle("Org Patterns")
        .task { await loadPatterns() }
    }

    private func loadPatterns() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await BackendService.shared.getCrossRepoPatterns()
            patterns = response.orgPatterns
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

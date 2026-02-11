import SwiftUI

struct KnowledgeRuleDetailView: View {
    let rule: KnowledgeRule
    @Bindable var vm: KnowledgeViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                Divider()
                ruleSection
                Divider()
                metadataSection
                if let detail = vm.ruleDetail, !detail.decisionTrail.isEmpty {
                    Divider()
                    decisionTrailSection(detail.decisionTrail)
                }
            }
            .padding(24)
        }
        .task {
            await vm.loadRuleDetail(id: rule.id)
        }
        .onChange(of: rule.id) { _, newId in
            Task { await vm.loadRuleDetail(id: newId) }
        }
        .navigationTitle("Rule Detail")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(rule.ruleText, forType: .string)
                } label: {
                    Label("Copy Rule", systemImage: "doc.on.doc")
                }
                .help("Copy rule text to clipboard")
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            ConfidenceMeter(confidence: rule.confidence)
            VStack(alignment: .leading, spacing: 4) {
                Text(rule.category)
                    .font(.headline)
                HStack(spacing: 8) {
                    SourceBadge(sourceType: rule.sourceType)
                    Text(rule.sourceRef)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
    }

    private var ruleSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Rule", systemImage: "text.quote")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
            Text(rule.ruleText)
                .font(.body)
                .textSelection(.enabled)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    private var metadataSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Metadata", systemImage: "info.circle")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                MetadataCard(label: "Confidence", value: "\(Int(rule.confidence * 100))%", icon: "chart.bar.fill")
                MetadataCard(label: "Category", value: rule.category, icon: "tag.fill")
                MetadataCard(label: "Source", value: rule.sourceType == .pr ? "Pull Request" : "Conversation", icon: "doc.fill")
                MetadataCard(label: "Created", value: rule.createdAt ?? "", icon: "calendar")
            }
        }
    }

    private func decisionTrailSection(_ trail: [DecisionTrail]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Decision Trail", systemImage: "point.topleft.down.to.point.bottomright.curvepath")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            ForEach(trail) { entry in
                HStack(alignment: .top, spacing: 12) {
                    Circle()
                        .fill(.blue)
                        .frame(width: 8, height: 8)
                        .padding(.top, 6)

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(entry.eventType)
                                .font(.caption)
                                .fontWeight(.semibold)
                                .textCase(.uppercase)
                                .foregroundStyle(.blue)
                            Spacer()
                            Text(entry.timestamp ?? "")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        Text(entry.description)
                            .font(.callout)
                        if !entry.sourceRef.isEmpty {
                            Text(entry.sourceRef)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }
}

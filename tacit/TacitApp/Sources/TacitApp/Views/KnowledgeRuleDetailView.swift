import SwiftUI

struct KnowledgeRuleDetailView: View {
    let rule: KnowledgeRule
    @Bindable var vm: KnowledgeViewModel
    @State private var feedbackScore: Int = 0
    @State private var isSendingFeedback = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                Divider()
                ruleSection
                Divider()
                feedbackSection
                Divider()
                metadataSection
                if let detail = vm.ruleDetail, !detail.decisionTrail.isEmpty {
                    Divider()
                    decisionTrailSection(detail.decisionTrail)
                }
            }
            .padding(24)
        }
        .onAppear { feedbackScore = rule.feedbackScore }
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
                Text(KnowledgeViewModel.displayName(for: rule.category))
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

    private var feedbackSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Feedback", systemImage: "hand.thumbsup")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            HStack(spacing: 16) {
                Button {
                    Task { await sendFeedback(vote: "up") }
                } label: {
                    Label("Helpful", systemImage: "hand.thumbsup.fill")
                        .foregroundStyle(.green)
                }
                .buttonStyle(.bordered)
                .disabled(isSendingFeedback)

                Button {
                    Task { await sendFeedback(vote: "down") }
                } label: {
                    Label("Not Helpful", systemImage: "hand.thumbsdown.fill")
                        .foregroundStyle(.red)
                }
                .buttonStyle(.bordered)
                .disabled(isSendingFeedback)

                Spacer()

                HStack(spacing: 4) {
                    Image(systemName: feedbackScore >= 0 ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                        .foregroundStyle(feedbackScore > 0 ? .green : feedbackScore < 0 ? .red : .secondary)
                    Text("\(feedbackScore)")
                        .font(.title3)
                        .fontWeight(.semibold)
                        .foregroundStyle(feedbackScore > 0 ? .green : feedbackScore < 0 ? .red : .secondary)
                }
            }
        }
    }

    private func sendFeedback(vote: String) async {
        isSendingFeedback = true
        defer { isSendingFeedback = false }
        do {
            let updated = try await BackendService.shared.sendFeedback(ruleId: rule.id, vote: vote)
            feedbackScore = updated.feedbackScore
        } catch {
            // Silently handle — feedback is non-critical
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
                MetadataCard(label: "Category", value: KnowledgeViewModel.displayName(for: rule.category), icon: "tag.fill")
                MetadataCard(label: "Source", value: sourceDisplayName(rule.sourceType), icon: "doc.fill")
                MetadataCard(label: "Created", value: rule.createdAt ?? "", icon: "calendar")
            }
        }
    }

    private func trailColor(for eventType: String) -> Color {
        switch eventType {
        case "created": return .blue
        case "approved": return .green
        case "rejected": return .red
        case "merged": return .orange
        case "confidence_boost": return .purple
        default: return .secondary
        }
    }

    private func trailIcon(for eventType: String) -> String {
        switch eventType {
        case "created": return "plus.circle.fill"
        case "approved": return "checkmark.circle.fill"
        case "rejected": return "xmark.circle.fill"
        case "merged": return "arrow.triangle.merge"
        case "confidence_boost": return "arrow.up.circle.fill"
        default: return "circle.fill"
        }
    }

    private func sourceDisplayName(_ type: KnowledgeRule.SourceType) -> String {
        switch type {
        case .pr: return "Pull Request"
        case .conversation: return "Conversation"
        case .structure: return "Repo Structure"
        case .docs: return "Documentation"
        case .cifix: return "CI Fix Pattern"
        case .config: return "Config Analysis"
        }
    }

    private func decisionTrailSection(_ trail: [DecisionTrail]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Decision Trail", systemImage: "point.topleft.down.to.point.bottomright.curvepath")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            ForEach(Array(trail.enumerated()), id: \.element.id) { index, entry in
                let color = trailColor(for: entry.eventType)
                HStack(alignment: .top, spacing: 12) {
                    VStack(spacing: 0) {
                        Image(systemName: trailIcon(for: entry.eventType))
                            .font(.system(size: 14))
                            .foregroundStyle(color)
                        if index < trail.count - 1 {
                            Rectangle()
                                .fill(color.opacity(0.3))
                                .frame(width: 2)
                                .frame(maxHeight: .infinity)
                        }
                    }
                    .frame(width: 20)

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(entry.eventType.replacingOccurrences(of: "_", with: " "))
                                .font(.caption)
                                .fontWeight(.semibold)
                                .textCase(.uppercase)
                                .foregroundStyle(color)
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

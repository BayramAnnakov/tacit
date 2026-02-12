import SwiftUI

struct ProposalReviewView: View {
    let proposal: Proposal
    @Bindable var vm: ProposalViewModel
    @State private var feedback = ""
    @State private var reviewerName = NSFullUserName()
    @State private var contributions: [ProposalContribution] = []
    @State private var isLoadingContributions = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                Divider()
                ruleSection
                sourceSection
                if proposal.contributorCount > 1 {
                    Divider()
                    consensusSection
                }
                if proposal.status == .pending {
                    Divider()
                    reviewSection
                }
                if !proposal.feedback.isEmpty {
                    Divider()
                    feedbackSection(proposal.feedback)
                }
            }
            .padding(24)
        }
        .navigationTitle("Review Proposal")
        .task(id: proposal.id) {
            if proposal.contributorCount > 1 {
                isLoadingContributions = true
                do {
                    contributions = try await BackendService.shared.getProposalContributions(proposalId: proposal.id)
                } catch {
                    contributions = []
                }
                isLoadingContributions = false
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            statusBadge
            VStack(alignment: .leading, spacing: 4) {
                Text(proposal.category)
                    .font(.headline)
                HStack(spacing: 8) {
                    ConfidenceBadge(confidence: proposal.confidence)
                    Text("Proposed by \(proposal.proposedBy)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Text(proposal.createdAt ?? "")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
    }

    private var statusBadge: some View {
        let (color, icon, label) = statusInfo
        return HStack(spacing: 4) {
            Image(systemName: icon)
            Text(label)
                .fontWeight(.medium)
        }
        .font(.caption)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(color.opacity(0.15))
        .foregroundStyle(color)
        .clipShape(Capsule())
    }

    private var statusInfo: (Color, String, String) {
        switch proposal.status {
        case .pending: return (.orange, "clock", "Pending")
        case .approved: return (.green, "checkmark.circle.fill", "Approved")
        case .rejected: return (.red, "xmark.circle.fill", "Rejected")
        }
    }

    private var ruleSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Proposed Rule", systemImage: "text.quote")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
            Text(proposal.ruleText)
                .font(.body)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    private var sourceSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Source Excerpt", systemImage: "doc.text")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
            Text(proposal.sourceExcerpt)
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.tertiary.opacity(0.3))
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    private var consensusSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Team Consensus", systemImage: "person.2.fill")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            Text("\(proposal.contributorCount) contributors independently discovered this pattern")
                .font(.callout)
                .foregroundStyle(.secondary)

            if isLoadingContributions {
                ProgressView()
                    .frame(maxWidth: .infinity)
            } else {
                VStack(spacing: 8) {
                    ForEach(contributions) { contribution in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: "person.circle.fill")
                                .foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(contribution.contributorName)
                                    .font(.caption)
                                    .fontWeight(.medium)
                                Text(contribution.originalRuleText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                                Text("\(Int(contribution.similarityScore * 100))% similar")
                                    .font(.caption2)
                                    .foregroundStyle(.green)
                            }
                            Spacer()
                        }
                        .padding(10)
                        .background(.quaternary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
        }
    }

    private var reviewSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Review", systemImage: "pencil.and.outline")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            TextField("Add feedback (optional)...", text: $feedback, axis: .vertical)
                .lineLimit(3...6)
                .textFieldStyle(.roundedBorder)

            HStack(spacing: 12) {
                Button {
                    Task {
                        await vm.approveProposal(
                            id: proposal.id,
                            feedback: feedback.isEmpty ? nil : feedback,
                            reviewedBy: reviewerName
                        )
                    }
                } label: {
                    Label("Approve", systemImage: "checkmark.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
                .controlSize(.large)

                Button {
                    Task {
                        await vm.rejectProposal(
                            id: proposal.id,
                            feedback: feedback.isEmpty ? nil : feedback,
                            reviewedBy: reviewerName
                        )
                    }
                } label: {
                    Label("Reject", systemImage: "xmark.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)
                .controlSize(.large)
            }
        }
    }

    private func feedbackSection(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Feedback", systemImage: "bubble.left.fill")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)

            HStack(alignment: .top, spacing: 8) {
                if !proposal.reviewedBy.isEmpty {
                    Text(proposal.reviewedBy)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                Text(text)
                    .font(.callout)
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary)
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }
}

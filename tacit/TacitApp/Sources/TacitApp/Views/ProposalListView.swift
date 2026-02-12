import SwiftUI

struct ProposalListView: View {
    @Bindable var vm: ProposalViewModel

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            Divider()
            proposalList
        }
        .navigationTitle("Proposals")
        .task {
            await vm.loadProposals()
        }
        .onChange(of: vm.statusFilter) { _, _ in
            Task { await vm.loadProposals() }
        }
    }

    private var filterBar: some View {
        HStack(spacing: 8) {
            ForEach(["pending", "approved", "rejected", nil] as [String?], id: \.self) { status in
                let label = status?.capitalized ?? "All"
                Button {
                    vm.statusFilter = status
                } label: {
                    Text(label)
                        .font(.caption)
                        .fontWeight(vm.statusFilter == status ? .semibold : .regular)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(vm.statusFilter == status ? statusColor(status).opacity(0.15) : .clear)
                        .foregroundStyle(vm.statusFilter == status ? statusColor(status) : .secondary)
                        .clipShape(Capsule())
                        .overlay(
                            Capsule()
                                .stroke(vm.statusFilter == status ? statusColor(status).opacity(0.3) : .secondary.opacity(0.2), lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding()
    }

    private func statusColor(_ status: String?) -> Color {
        switch status {
        case "pending": return .orange
        case "approved": return .green
        case "rejected": return .red
        default: return .blue
        }
    }

    private var proposalList: some View {
        Group {
            if vm.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.proposals.isEmpty {
                EmptyStateView(
                    icon: "arrow.up.doc",
                    title: "No Proposals",
                    message: "Knowledge proposals from team members will appear here for review."
                )
            } else {
                List(vm.proposals, selection: $vm.selectedProposal) { proposal in
                    ProposalCardView(proposal: proposal)
                        .tag(proposal)
                }
                .listStyle(.inset)
            }
        }
    }
}

struct ProposalCardView: View {
    let proposal: Proposal

    var statusColor: Color {
        switch proposal.status {
        case .pending: return .orange
        case .approved: return .green
        case .rejected: return .red
        }
    }

    var statusIcon: String {
        switch proposal.status {
        case .pending: return "clock"
        case .approved: return "checkmark.circle.fill"
        case .rejected: return "xmark.circle.fill"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                Text(proposal.ruleText)
                    .font(.callout)
                    .lineLimit(2)
                Spacer()
                Image(systemName: statusIcon)
                    .foregroundStyle(statusColor)
            }

            HStack(spacing: 6) {
                CategoryPill(category: proposal.category)
                ConfidenceBadge(confidence: proposal.confidence)
                if proposal.contributorCount > 1 {
                    ConsensusIndicator(count: proposal.contributorCount)
                }
                Spacer()
                Text("by \(proposal.proposedBy)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

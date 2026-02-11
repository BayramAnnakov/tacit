import Foundation

@Observable
final class ProposalViewModel {
    var proposals: [Proposal] = []
    var selectedProposal: Proposal?
    var statusFilter: String? = "pending"
    var isLoading = false

    /// Called when a proposal is approved or rejected
    var onProposalReviewed: (() -> Void)?

    private let backend = BackendService.shared

    func loadProposals() async {
        isLoading = true
        defer { isLoading = false }
        do {
            proposals = try await backend.listProposals(status: statusFilter)
        } catch {
            proposals = []
        }
    }

    func createProposal(ruleText: String, category: String, confidence: Double, sourceExcerpt: String, proposedBy: String) async {
        let proposal = NewProposal(
            ruleText: ruleText,
            category: category,
            confidence: confidence,
            sourceExcerpt: sourceExcerpt,
            proposedBy: proposedBy
        )
        do {
            let created = try await backend.createProposal(proposal)
            proposals.insert(created, at: 0)
        } catch {
            // Error handled silently
        }
    }

    func approveProposal(id: Int, feedback: String?, reviewedBy: String) async {
        do {
            let updated = try await backend.reviewProposal(id: id, status: "approved", feedback: feedback, reviewedBy: reviewedBy)
            if let index = proposals.firstIndex(where: { $0.id == id }) {
                proposals[index] = updated
            }
            selectedProposal = updated
            onProposalReviewed?()
        } catch {
            // Error handled silently
        }
    }

    func rejectProposal(id: Int, feedback: String?, reviewedBy: String) async {
        do {
            let updated = try await backend.reviewProposal(id: id, status: "rejected", feedback: feedback, reviewedBy: reviewedBy)
            if let index = proposals.firstIndex(where: { $0.id == id }) {
                proposals[index] = updated
            }
            selectedProposal = updated
            onProposalReviewed?()
        } catch {
            // Error handled silently
        }
    }
}

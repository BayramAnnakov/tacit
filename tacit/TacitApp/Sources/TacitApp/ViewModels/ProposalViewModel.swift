import Foundation

@Observable
final class ProposalViewModel {
    var proposals: [Proposal] = []
    var selectedProposal: Proposal?
    var statusFilter: String? = "pending"
    var isLoading = false
    var errorMessage: String?

    /// Called when a proposal is approved or rejected
    var onProposalReviewed: (() -> Void)?

    private let backend = BackendService.shared

    func loadProposals() async {
        isLoading = true
        defer { isLoading = false }
        do {
            proposals = try await backend.listProposals(status: statusFilter)
            errorMessage = nil
        } catch {
            proposals = []
            errorMessage = error.localizedDescription
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
            errorMessage = nil
        } catch {
            errorMessage = "Failed to create proposal: \(error.localizedDescription)"
        }
    }

    func approveProposal(id: Int, feedback: String?, reviewedBy: String) async {
        do {
            let updated = try await backend.reviewProposal(id: id, status: "approved", feedback: feedback, reviewedBy: reviewedBy)
            if let index = proposals.firstIndex(where: { $0.id == id }) {
                proposals[index] = updated
            }
            selectedProposal = updated
            errorMessage = nil
            onProposalReviewed?()
        } catch {
            errorMessage = "Failed to approve proposal: \(error.localizedDescription)"
        }
    }

    func rejectProposal(id: Int, feedback: String?, reviewedBy: String) async {
        do {
            let updated = try await backend.reviewProposal(id: id, status: "rejected", feedback: feedback, reviewedBy: reviewedBy)
            if let index = proposals.firstIndex(where: { $0.id == id }) {
                proposals[index] = updated
            }
            selectedProposal = updated
            errorMessage = nil
            onProposalReviewed?()
        } catch {
            errorMessage = "Failed to reject proposal: \(error.localizedDescription)"
        }
    }
}

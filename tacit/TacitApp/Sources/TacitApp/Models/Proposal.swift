import Foundation

struct Proposal: Codable, Identifiable, Hashable {
    let id: Int
    var ruleText: String
    var category: String
    var confidence: Double
    var sourceExcerpt: String
    var proposedBy: String
    var status: ProposalStatus
    var feedback: String
    var reviewedBy: String
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case ruleText = "rule_text"
        case category, confidence
        case sourceExcerpt = "source_excerpt"
        case proposedBy = "proposed_by"
        case status, feedback
        case reviewedBy = "reviewed_by"
        case createdAt = "created_at"
    }

    enum ProposalStatus: String, Codable, Hashable {
        case pending
        case approved
        case rejected
    }
}

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
    var contributorCount: Int
    var repoId: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case ruleText = "rule_text"
        case category, confidence
        case sourceExcerpt = "source_excerpt"
        case proposedBy = "proposed_by"
        case status, feedback
        case reviewedBy = "reviewed_by"
        case createdAt = "created_at"
        case contributorCount = "contributor_count"
        case repoId = "repo_id"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        ruleText = try container.decode(String.self, forKey: .ruleText)
        category = try container.decode(String.self, forKey: .category)
        confidence = try container.decode(Double.self, forKey: .confidence)
        sourceExcerpt = try container.decode(String.self, forKey: .sourceExcerpt)
        proposedBy = try container.decode(String.self, forKey: .proposedBy)
        status = try container.decode(ProposalStatus.self, forKey: .status)
        feedback = try container.decode(String.self, forKey: .feedback)
        reviewedBy = try container.decode(String.self, forKey: .reviewedBy)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        contributorCount = try container.decodeIfPresent(Int.self, forKey: .contributorCount) ?? 1
        repoId = try container.decodeIfPresent(Int.self, forKey: .repoId)
    }

    enum ProposalStatus: String, Codable, Hashable {
        case pending
        case approved
        case rejected
    }
}

struct ProposalContribution: Codable, Identifiable {
    let id: Int
    var proposalId: Int
    var contributorName: String
    var originalRuleText: String
    var originalConfidence: Double
    var sourceExcerpt: String
    var similarityScore: Double
    var contributedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case proposalId = "proposal_id"
        case contributorName = "contributor_name"
        case originalRuleText = "original_rule_text"
        case originalConfidence = "original_confidence"
        case sourceExcerpt = "source_excerpt"
        case similarityScore = "similarity_score"
        case contributedAt = "contributed_at"
    }
}

import Foundation

struct KnowledgeRule: Codable, Identifiable, Hashable {
    let id: Int
    var ruleText: String
    var category: String
    var confidence: Double
    var sourceType: SourceType
    var sourceRef: String
    var repoId: Int?
    var createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case ruleText = "rule_text"
        case category, confidence
        case sourceType = "source_type"
        case sourceRef = "source_ref"
        case repoId = "repo_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    enum SourceType: String, Codable, Hashable {
        case pr
        case conversation
    }
}

struct KnowledgeRuleDetail: Codable {
    let rule: KnowledgeRule
    let decisionTrail: [DecisionTrail]

    enum CodingKeys: String, CodingKey {
        case rule
        case decisionTrail = "decision_trail"
    }
}

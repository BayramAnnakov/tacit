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
    var feedbackScore: Int

    enum CodingKeys: String, CodingKey {
        case id
        case ruleText = "rule_text"
        case category, confidence
        case sourceType = "source_type"
        case sourceRef = "source_ref"
        case repoId = "repo_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case feedbackScore = "feedback_score"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        ruleText = try container.decode(String.self, forKey: .ruleText)
        category = try container.decode(String.self, forKey: .category)
        confidence = try container.decode(Double.self, forKey: .confidence)
        sourceType = try container.decode(SourceType.self, forKey: .sourceType)
        sourceRef = try container.decode(String.self, forKey: .sourceRef)
        repoId = try container.decodeIfPresent(Int.self, forKey: .repoId)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        feedbackScore = try container.decodeIfPresent(Int.self, forKey: .feedbackScore) ?? 0
    }

    enum SourceType: String, Codable, Hashable {
        case pr
        case conversation
        case structure
        case docs
        case cifix = "ci_fix"
        case config
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

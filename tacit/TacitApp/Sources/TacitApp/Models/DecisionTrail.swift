import Foundation

struct DecisionTrail: Codable, Identifiable, Hashable {
    let id: Int
    var ruleId: Int
    var eventType: String
    var description: String
    var sourceRef: String
    var timestamp: String?

    enum CodingKeys: String, CodingKey {
        case id
        case ruleId = "rule_id"
        case eventType = "event_type"
        case description
        case sourceRef = "source_ref"
        case timestamp
    }
}

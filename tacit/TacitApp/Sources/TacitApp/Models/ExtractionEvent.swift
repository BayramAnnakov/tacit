import Foundation

struct ExtractionEvent: Codable, Identifiable, Hashable {
    var id = UUID()
    var type: EventType
    var data: [String: String]
    var timestamp: Date

    enum CodingKeys: String, CodingKey {
        case type, data, timestamp
    }

    enum EventType: String, Codable, Hashable {
        case ruleDiscovered = "rule_discovered"
        case analyzing
        case patternMerged = "pattern_merged"
        case stageComplete = "stage_complete"
        case error
        case info
    }

    init(type: EventType, data: [String: String], timestamp: Date = .now) {
        self.id = UUID()
        self.type = type
        self.data = data
        self.timestamp = timestamp
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoFormatterNoFrac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.type = try container.decode(EventType.self, forKey: .type)
        self.data = try container.decodeIfPresent([String: String].self, forKey: .data) ?? [:]

        // Parse ISO 8601 timestamp string from backend
        if let tsString = try container.decodeIfPresent(String.self, forKey: .timestamp),
           let date = Self.isoFormatter.date(from: tsString) ?? Self.isoFormatterNoFrac.date(from: tsString) {
            self.timestamp = date
        } else {
            self.timestamp = .now
        }
    }
}

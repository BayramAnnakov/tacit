import Foundation

struct Repository: Codable, Identifiable, Hashable {
    let id: Int
    var owner: String
    var name: String
    var fullName: String
    var githubUrl: String
    var connectedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, owner, name
        case fullName = "full_name"
        case githubUrl = "github_url"
        case connectedAt = "connected_at"
    }
}

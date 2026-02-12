import Foundation

@Observable
final class BackendService {
    static let shared = BackendService()

    private let baseURL = "http://localhost:8000"
    private let wsURL = "ws://localhost:8000/ws"
    private var webSocketTask: URLSessionWebSocketTask?
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    var isConnected = false

    var onExtractionEvent: ((ExtractionEvent) -> Void)?

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()

        self.encoder = JSONEncoder()
    }

    // MARK: - Repositories

    func listRepos() async throws -> [Repository] {
        let data = try await get("/api/repos")
        return try decoder.decode([Repository].self, from: data)
    }

    func addRepo(owner: String, name: String, githubToken: String = "") async throws -> Repository {
        let body = ["owner": owner, "name": name, "github_token": githubToken]
        let data = try await post("/api/repos", body: body)
        return try decoder.decode(Repository.self, from: data)
    }

    // MARK: - Extraction

    func startExtraction(repoId: Int) async throws {
        _ = try await post("/api/extract/\(repoId)", body: Optional<String>.none)
    }

    func startLocalExtraction(projectPath: String) async throws {
        let body = ["project_path": projectPath]
        _ = try await post("/api/local-extract", body: body)
    }

    // MARK: - Knowledge

    func listKnowledge(repoId: Int? = nil, category: String? = nil, search: String? = nil) async throws -> [KnowledgeRule] {
        var params: [String] = []
        if let repoId { params.append("repo_id=\(repoId)") }
        if let category, !category.isEmpty { params.append("category=\(category)") }
        if let search, !search.isEmpty {
            params.append("q=\(search.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? search)")
        }
        let query = params.isEmpty ? "" : "?\(params.joined(separator: "&"))"
        let data = try await get("/api/knowledge\(query)")
        return try decoder.decode([KnowledgeRule].self, from: data)
    }

    func getKnowledgeDetail(id: Int) async throws -> KnowledgeRuleDetail {
        let data = try await get("/api/knowledge/\(id)")
        return try decoder.decode(KnowledgeRuleDetail.self, from: data)
    }

    // MARK: - Proposals

    func listProposals(status: String? = nil) async throws -> [Proposal] {
        let query = status.map { "?status=\($0)" } ?? ""
        let data = try await get("/api/proposals\(query)")
        return try decoder.decode([Proposal].self, from: data)
    }

    func createProposal(_ proposal: NewProposal) async throws -> Proposal {
        let data = try await post("/api/proposals", body: proposal)
        return try decoder.decode(Proposal.self, from: data)
    }

    func reviewProposal(id: Int, status: String, feedback: String?, reviewedBy: String) async throws -> Proposal {
        var body: [String: String] = ["status": status, "reviewed_by": reviewedBy]
        if let feedback { body["feedback"] = feedback }
        let data = try await put("/api/proposals/\(id)", body: body)
        return try decoder.decode(Proposal.self, from: data)
    }

    func getProposalContributions(proposalId: Int) async throws -> [ProposalContribution] {
        let data = try await get("/api/proposals/\(proposalId)/contributions")
        let response = try decoder.decode(ProposalContributionsResponse.self, from: data)
        return response.contributions
    }

    func contribute(contributorName: String, rules: [ContributeRule], projectHint: String = "") async throws -> ContributeResponse {
        let payload = ContributePayload(
            contributor_name: contributorName,
            rules: rules,
            project_hint: projectHint,
            client_version: "0.1.0"
        )
        let data = try await post("/api/contribute", body: payload)
        return try decoder.decode(ContributeResponse.self, from: data)
    }

    // MARK: - CLAUDE.md

    func getClaudeMD(repoId: Int) async throws -> String {
        let data = try await get("/api/claude-md/\(repoId)")
        let response = try decoder.decode(ClaudeMDResponse.self, from: data)
        return response.content
    }

    func getClaudeMDDiff(repoId: Int) async throws -> ClaudeMDDiffResponse {
        let data = try await get("/api/claude-md/\(repoId)/diff")
        return try decoder.decode(ClaudeMDDiffResponse.self, from: data)
    }

    func createPR(repoId: Int, content: String, branchName: String = "tacit/update-claude-md") async throws -> CreatePRResponse {
        struct Body: Encodable {
            let content: String
            let branch_name: String
        }
        let data = try await post("/api/claude-md/\(repoId)/create-pr", body: Body(content: content, branch_name: branchName))
        return try decoder.decode(CreatePRResponse.self, from: data)
    }

    // MARK: - Feedback

    func sendFeedback(ruleId: Int, vote: String) async throws -> KnowledgeRule {
        struct Body: Encodable { let vote: String }
        let data = try await post("/api/knowledge/\(ruleId)/feedback", body: Body(vote: vote))
        return try decoder.decode(KnowledgeRule.self, from: data)
    }

    // MARK: - Cross-Repo Intelligence

    func getCrossRepoPatterns() async throws -> CrossRepoResponse {
        let data = try await get("/api/knowledge/cross-repo")
        return try decoder.decode(CrossRepoResponse.self, from: data)
    }

    // MARK: - WebSocket

    func connectWebSocket() {
        guard let url = URL(string: wsURL) else { return }
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        isConnected = true
        receiveMessage()
    }

    func disconnectWebSocket() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        isConnected = false
    }

    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    if let data = text.data(using: .utf8),
                       let event = try? self.decoder.decode(ExtractionEvent.self, from: data) {
                        DispatchQueue.main.async {
                            self.onExtractionEvent?(event)
                        }
                    }
                default:
                    break
                }
                self.receiveMessage()
            case .failure:
                DispatchQueue.main.async {
                    self.isConnected = false
                }
            }
        }
    }

    // MARK: - HTTP Helpers

    private func get(_ path: String) async throws -> Data {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw BackendError.invalidURL
        }
        let (data, response) = try await session.data(from: url)
        try validateResponse(response)
        return data
    }

    private func post<T: Encodable>(_ path: String, body: T?) async throws -> Data {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw BackendError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body {
            request.httpBody = try encoder.encode(body)
        }
        let (data, response) = try await session.data(for: request)
        try validateResponse(response)
        return data
    }

    private func put<T: Encodable>(_ path: String, body: T) async throws -> Data {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw BackendError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await session.data(for: request)
        try validateResponse(response)
        return data
    }

    private func validateResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            throw BackendError.httpError(http.statusCode)
        }
    }
}

enum BackendError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid response from server"
        case .httpError(let code): return "HTTP error \(code)"
        }
    }
}

struct NewProposal: Codable {
    var ruleText: String
    var category: String
    var confidence: Double
    var sourceExcerpt: String
    var proposedBy: String

    enum CodingKeys: String, CodingKey {
        case ruleText = "rule_text"
        case category, confidence
        case sourceExcerpt = "source_excerpt"
        case proposedBy = "proposed_by"
    }
}

struct ClaudeMDResponse: Codable {
    var content: String
}

struct DiffLine: Codable, Identifiable {
    let id: UUID
    let type: String
    let text: String

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.type = try container.decode(String.self, forKey: .type)
        self.text = try container.decode(String.self, forKey: .text)
    }

    enum CodingKeys: String, CodingKey {
        case type, text
    }
}

struct ClaudeMDDiffResponse: Codable {
    let existing: String
    let generated: String
    let diffLines: [DiffLine]

    enum CodingKeys: String, CodingKey {
        case existing, generated
        case diffLines = "diff_lines"
    }
}

struct CreatePRResponse: Codable {
    let prUrl: String
    let prNumber: Int
    let branchName: String

    enum CodingKeys: String, CodingKey {
        case prUrl = "pr_url"
        case prNumber = "pr_number"
        case branchName = "branch_name"
    }
}

struct OrgPattern: Codable, Identifiable {
    var id: String { ruleText }
    let ruleText: String
    let repos: [String]
    let frequency: Int
    let category: String

    enum CodingKeys: String, CodingKey {
        case ruleText = "rule_text"
        case repos, frequency, category
    }
}

struct CrossRepoResponse: Codable {
    let orgPatterns: [OrgPattern]

    enum CodingKeys: String, CodingKey {
        case orgPatterns = "org_patterns"
    }
}

struct ProposalContributionsResponse: Codable {
    let proposalId: Int
    let contributions: [ProposalContribution]

    enum CodingKeys: String, CodingKey {
        case proposalId = "proposal_id"
        case contributions
    }
}

struct ContributePayload: Encodable {
    let contributor_name: String
    let rules: [ContributeRule]
    let project_hint: String
    let client_version: String
}

struct ContributeRule: Encodable {
    let rule_text: String
    let category: String
    let confidence: Double
    let source_excerpt: String
}

struct ContributeResponse: Codable {
    let accepted: Int
    let results: [ContributeResult]
}

struct ContributeResult: Codable {
    let action: String
    let proposalId: Int
    let contributorCount: Int
    let similarityScore: Double?

    enum CodingKeys: String, CodingKey {
        case action
        case proposalId = "proposal_id"
        case contributorCount = "contributor_count"
        case similarityScore = "similarity_score"
    }
}

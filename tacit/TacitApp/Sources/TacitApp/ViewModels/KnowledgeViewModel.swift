import Foundation

@Observable
final class KnowledgeViewModel {
    var rules: [KnowledgeRule] = []
    var selectedRule: KnowledgeRule?
    var ruleDetail: KnowledgeRuleDetail?
    var searchText = ""
    var selectedCategory = ""
    var isLoading = false

    let categories = ["", "architecture", "style", "testing", "workflow", "performance", "security", "general"]

    /// Display name for a category value
    static func displayName(for category: String) -> String {
        if category.isEmpty { return "All" }
        return category.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private let backend = BackendService.shared
    private var searchDebounceTask: Task<Void, Never>?

    func loadRules(repoId: Int? = nil) async {
        isLoading = true
        defer { isLoading = false }
        do {
            rules = try await backend.listKnowledge(
                repoId: repoId,
                category: selectedCategory.isEmpty ? nil : selectedCategory,
                search: searchText.isEmpty ? nil : searchText
            )
        } catch {
            rules = []
        }
    }

    func debouncedSearch(repoId: Int? = nil) {
        searchDebounceTask?.cancel()
        searchDebounceTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await loadRules(repoId: repoId)
        }
    }

    func loadRuleDetail(id: Int) async {
        do {
            ruleDetail = try await backend.getKnowledgeDetail(id: id)
        } catch {
            ruleDetail = nil
        }
    }
}

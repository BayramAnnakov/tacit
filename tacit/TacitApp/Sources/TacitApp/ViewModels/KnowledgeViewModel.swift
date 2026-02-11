import Foundation

@Observable
final class KnowledgeViewModel {
    var rules: [KnowledgeRule] = []
    var selectedRule: KnowledgeRule?
    var ruleDetail: KnowledgeRuleDetail?
    var searchText = ""
    var selectedCategory = ""
    var isLoading = false

    let categories = ["", "Architecture", "Code Style", "Testing", "Error Handling", "Performance", "Security", "Documentation", "Dependencies", "DevOps"]

    private let backend = BackendService.shared

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

    func loadRuleDetail(id: Int) async {
        do {
            ruleDetail = try await backend.getKnowledgeDetail(id: id)
        } catch {
            ruleDetail = nil
        }
    }
}

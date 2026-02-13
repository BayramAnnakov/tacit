import Foundation
import SwiftUI

enum SidebarItem: Hashable {
    case teamKnowledge
    case myDiscoveries
    case proposals
    case claudeMD
    case orgPatterns
    case repo(Repository)
    case extraction
    case hooks
    case metrics
    case health
}

@Observable
final class AppViewModel {
    var selectedSidebarItem: SidebarItem? = .teamKnowledge
    var repos: [Repository] = []
    var isLoadingRepos = false
    var showAddRepoSheet = false
    var errorMessage: String?
    var showError = false

    private let backend = BackendService.shared

    func loadRepos() async {
        isLoadingRepos = true
        defer { isLoadingRepos = false }
        do {
            repos = try await backend.listRepos()
        } catch {
            showErrorMessage(error.localizedDescription)
        }
    }

    func addRepo(url: String, token: String?) async {
        // Parse owner/name from GitHub URL like "https://github.com/owner/repo" or "owner/repo"
        let parts: [String]
        if url.contains("github.com") {
            let cleaned = url
                .replacingOccurrences(of: "https://github.com/", with: "")
                .replacingOccurrences(of: "http://github.com/", with: "")
                .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            parts = cleaned.split(separator: "/").map(String.init)
        } else {
            parts = url.split(separator: "/").map(String.init)
        }

        guard parts.count >= 2 else {
            showErrorMessage("Invalid repository URL. Use format: owner/repo or https://github.com/owner/repo")
            return
        }

        do {
            let repo = try await backend.addRepo(owner: parts[0], name: parts[1], githubToken: token ?? "")
            repos.append(repo)
        } catch {
            showErrorMessage(error.localizedDescription)
        }
    }

    private func showErrorMessage(_ message: String) {
        errorMessage = message
        showError = true
    }
}

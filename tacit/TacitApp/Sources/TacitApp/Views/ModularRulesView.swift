import SwiftUI

struct ModularRulesView: View {
    let repos: [Repository]
    @State private var selectedRepoId: Int?
    @State private var files: [String: String] = [:]
    @State private var selectedFile: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    private let backend = BackendService.shared

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if repos.isEmpty {
                ContentUnavailableView(
                    "No Repositories",
                    systemImage: "folder.badge.questionmark",
                    description: Text("Connect a repository first to generate modular rules.")
                )
            } else if isLoading {
                ProgressView("Generating .claude/rules/...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorMessage {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(errorMessage)
                )
            } else if files.isEmpty {
                ContentUnavailableView(
                    "No Rules Generated",
                    systemImage: "folder.badge.gearshape",
                    description: Text("Select a repository and tap Generate to create path-scoped rule files.")
                )
            } else {
                fileList
            }
        }
    }

    private var header: some View {
        HStack {
            Picker("Repository", selection: $selectedRepoId) {
                Text("Select...").tag(nil as Int?)
                ForEach(repos) { repo in
                    Text(repo.fullName).tag(repo.id as Int?)
                }
            }
            .frame(maxWidth: 250)

            Button("Generate") {
                guard let repoId = selectedRepoId else { return }
                Task { await generateRules(repoId: repoId) }
            }
            .disabled(selectedRepoId == nil || isLoading)

            Spacer()

            if !files.isEmpty {
                Text("\(files.count) files")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }

    private var fileList: some View {
        List(sortedFileNames, id: \.self, selection: $selectedFile) { fileName in
            VStack(alignment: .leading, spacing: 4) {
                Label(fileName, systemImage: iconName(for: fileName))
                    .font(.system(.body, design: .monospaced))

                if let content = files[fileName] {
                    Text(content.prefix(120) + (content.count > 120 ? "..." : ""))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var sortedFileNames: [String] {
        files.keys.sorted()
    }

    private func iconName(for fileName: String) -> String {
        if fileName.contains("do-not") { return "xmark.octagon" }
        if fileName.contains("domain") { return "building.2" }
        if fileName.contains("design") { return "paintbrush" }
        if fileName.contains("product") { return "lightbulb" }
        return "doc.text"
    }

    private func generateRules(repoId: Int) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await backend.getModularRules(repoId: repoId)
            files = response.files
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

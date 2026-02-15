import SwiftUI

struct OnboardingView: View {
    let repos: [Repository]
    @State private var developerName = ""
    @State private var role = "engineer"
    @State private var selectedRepoIds: Set<Int> = []
    @State private var generatedContent: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    private let backend = BackendService.shared
    private let roles = ["engineer", "frontend", "backend", "fullstack", "devops", "qa", "manager"]

    var body: some View {
        VStack(spacing: 0) {
            formSection
            Divider()
            resultSection
        }
    }

    private var formSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Generate Onboarding Guide")
                .font(.headline)

            HStack(spacing: 16) {
                TextField("Developer name", text: $developerName)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 200)

                Picker("Role", selection: $role) {
                    ForEach(roles, id: \.self) { r in
                        Text(r.capitalized).tag(r)
                    }
                }
                .frame(maxWidth: 150)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Repositories")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                ForEach(repos) { repo in
                    Toggle(repo.fullName, isOn: Binding(
                        get: { selectedRepoIds.contains(repo.id) },
                        set: { isSelected in
                            if isSelected {
                                selectedRepoIds.insert(repo.id)
                            } else {
                                selectedRepoIds.remove(repo.id)
                            }
                        }
                    ))
                    .toggleStyle(.checkbox)
                }
            }

            Button("Generate Guide") {
                Task { await generate() }
            }
            .disabled(developerName.isEmpty || selectedRepoIds.isEmpty || isLoading)
        }
        .padding()
    }

    @ViewBuilder
    private var resultSection: some View {
        if isLoading {
            ProgressView("Generating personalized onboarding guide...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let errorMessage {
            ContentUnavailableView(
                "Error",
                systemImage: "exclamationmark.triangle",
                description: Text(errorMessage)
            )
        } else if let content = generatedContent {
            ScrollView {
                Text(content)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .overlay(alignment: .topTrailing) {
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(content, forType: .string)
                } label: {
                    Image(systemName: "doc.on.doc")
                }
                .padding(8)
            }
        } else {
            ContentUnavailableView(
                "No Guide Generated",
                systemImage: "person.badge.plus",
                description: Text("Fill in the developer details and select repositories to generate a personalized onboarding guide.")
            )
        }
    }

    private func generate() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await backend.generateOnboarding(
                name: developerName,
                role: role,
                repoIds: Array(selectedRepoIds)
            )
            generatedContent = response.content
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

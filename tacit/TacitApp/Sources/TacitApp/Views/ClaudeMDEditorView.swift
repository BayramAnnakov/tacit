import SwiftUI
import UniformTypeIdentifiers

struct ClaudeMDEditorView: View {
    @State private var content = ""
    @State private var isLoading = false
    @State private var selectedRepoId: Int?
    let repos: [Repository]

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Generating CLAUDE.md...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if content.isEmpty {
                EmptyStateView(
                    icon: "doc.text",
                    title: "CLAUDE.md Generator",
                    message: "Select a repository and click Generate to create a CLAUDE.md file from discovered team knowledge."
                )
            } else {
                HSplitView {
                    previewPane
                    editorPane
                }
            }
        }
        .navigationTitle("CLAUDE.md")
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("Repository", selection: $selectedRepoId) {
                    Text("Select Repository").tag(nil as Int?)
                    ForEach(repos) { repo in
                        Text(repo.name).tag(repo.id as Int?)
                    }
                }
                .frame(width: 200)
            }
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    guard let repoId = selectedRepoId else { return }
                    Task {
                        isLoading = true
                        do {
                            content = try await BackendService.shared.getClaudeMD(repoId: repoId)
                        } catch {
                            content = "# Error\nFailed to generate CLAUDE.md: \(error.localizedDescription)"
                        }
                        isLoading = false
                    }
                } label: {
                    Label("Generate", systemImage: "arrow.clockwise")
                }
                .disabled(selectedRepoId == nil)
                .help("Generate CLAUDE.md from team knowledge")

                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(content, forType: .string)
                } label: {
                    Label("Copy", systemImage: "doc.on.doc")
                }
                .disabled(content.isEmpty)
                .help("Copy to clipboard")

                Button {
                    exportFile()
                } label: {
                    Label("Export", systemImage: "square.and.arrow.up")
                }
                .disabled(content.isEmpty)
                .keyboardShortcut("e", modifiers: .command)
                .help("Export as file")
            }
        }
    }

    private var previewPane: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(content.components(separatedBy: "\n").enumerated()), id: \.offset) { _, line in
                    if line.hasPrefix("# ") {
                        Text(line.dropFirst(2))
                            .font(.title)
                            .fontWeight(.bold)
                            .padding(.top, 8)
                    } else if line.hasPrefix("## ") {
                        Text(line.dropFirst(3))
                            .font(.title2)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.accentColor)
                            .padding(.top, 12)
                    } else if line.hasPrefix("### ") {
                        Text(line.dropFirst(4))
                            .font(.title3)
                            .fontWeight(.medium)
                            .padding(.top, 8)
                    } else if line.hasPrefix("- ") {
                        HStack(alignment: .top, spacing: 6) {
                            Text("\u{2022}")
                                .foregroundStyle(.secondary)
                            Text(line.dropFirst(2))
                                .textSelection(.enabled)
                        }
                        .padding(.leading, 8)
                    } else if !line.isEmpty {
                        Text(line)
                            .textSelection(.enabled)
                    }
                }
            }
            .font(.system(.body, design: .default))
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(minWidth: 300)
        .background(.background)
    }

    private var editorPane: some View {
        TextEditor(text: $content)
            .font(.system(.body, design: .monospaced))
            .frame(minWidth: 300)
    }

    private func exportFile() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "CLAUDE.md"
        panel.allowedContentTypes = [.plainText]
        panel.begin { response in
            if response == .OK, let url = panel.url {
                try? content.write(to: url, atomically: true, encoding: .utf8)
            }
        }
    }
}

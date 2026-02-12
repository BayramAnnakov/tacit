import SwiftUI
import UniformTypeIdentifiers

enum ClaudeMDViewMode: String, CaseIterable {
    case full = "Full"
    case diff = "Diff"
}

struct ClaudeMDEditorView: View {
    @State private var content = ""
    @State private var isLoading = false
    @State private var selectedRepoId: Int?
    @State private var viewMode: ClaudeMDViewMode = .full
    @State private var diffResponse: ClaudeMDDiffResponse?
    @State private var showPRSuccess = false
    @State private var prURL = ""
    @State private var isCreatingPR = false
    let repos: [Repository]

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Generating CLAUDE.md...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if content.isEmpty && diffResponse == nil {
                EmptyStateView(
                    icon: "doc.text",
                    title: "CLAUDE.md Generator",
                    message: "Select a repository and click Generate to create a CLAUDE.md file from discovered team knowledge."
                )
            } else {
                switch viewMode {
                case .full:
                    HSplitView {
                        previewPane
                        editorPane
                    }
                case .diff:
                    diffPane
                }
            }
        }
        .navigationTitle("CLAUDE.md")
        .toolbar {
            ToolbarItem(placement: .principal) {
                HStack(spacing: 12) {
                    Picker("Repository", selection: $selectedRepoId) {
                        Text("Select Repository").tag(nil as Int?)
                        ForEach(repos) { repo in
                            Text(repo.name).tag(repo.id as Int?)
                        }
                    }
                    .frame(width: 200)

                    Picker("View", selection: $viewMode) {
                        ForEach(ClaudeMDViewMode.allCases, id: \.self) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 120)
                }
            }
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    guard let repoId = selectedRepoId else { return }
                    Task {
                        isLoading = true
                        do {
                            if viewMode == .diff {
                                diffResponse = try await BackendService.shared.getClaudeMDDiff(repoId: repoId)
                                content = diffResponse?.generated ?? ""
                            } else {
                                content = try await BackendService.shared.getClaudeMD(repoId: repoId)
                            }
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
                    guard let repoId = selectedRepoId else { return }
                    isCreatingPR = true
                    Task {
                        do {
                            let result = try await BackendService.shared.createPR(repoId: repoId, content: content)
                            prURL = result.prUrl
                            showPRSuccess = true
                        } catch {
                            content = "# Error creating PR\n\(error.localizedDescription)"
                        }
                        isCreatingPR = false
                    }
                } label: {
                    if isCreatingPR {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label("Create PR", systemImage: "arrow.triangle.pull")
                    }
                }
                .disabled(content.isEmpty || selectedRepoId == nil || isCreatingPR)
                .help("Create a GitHub PR with this CLAUDE.md")

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
        .alert("PR Created", isPresented: $showPRSuccess) {
            Button("Open in Browser") {
                if let url = URL(string: prURL) {
                    NSWorkspace.shared.open(url)
                }
            }
            Button("OK", role: .cancel) {}
        } message: {
            Text("Pull request created successfully.\n\(prURL)")
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

    private var diffPane: some View {
        ScrollView {
            if let diff = diffResponse {
                VStack(alignment: .leading, spacing: 0) {
                    // Diff header
                    HStack {
                        Label("Existing", systemImage: "doc.text")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("\(diff.diffLines.filter { $0.type == "add" }.count) additions, \(diff.diffLines.filter { $0.type == "remove" }.count) removals")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(.quaternary)

                    Divider()

                    // Diff lines
                    ForEach(diff.diffLines) { line in
                        HStack(spacing: 0) {
                            Text(diffPrefix(for: line.type))
                                .font(.system(.body, design: .monospaced))
                                .foregroundStyle(diffColor(for: line.type))
                                .frame(width: 20, alignment: .center)

                            Text(line.text)
                                .font(.system(.body, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 2)
                        .background(diffBackground(for: line.type))
                    }
                }
            } else {
                EmptyStateView(
                    icon: "arrow.left.arrow.right",
                    title: "No Diff Available",
                    message: "Click Generate to compare existing CLAUDE.md with generated version."
                )
            }
        }
    }

    private func diffPrefix(for type: String) -> String {
        switch type {
        case "add": return "+"
        case "remove": return "-"
        default: return " "
        }
    }

    private func diffColor(for type: String) -> Color {
        switch type {
        case "add": return .green
        case "remove": return .red
        default: return .primary
        }
    }

    private func diffBackground(for type: String) -> Color {
        switch type {
        case "add": return .green.opacity(0.1)
        case "remove": return .red.opacity(0.1)
        default: return .clear
        }
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

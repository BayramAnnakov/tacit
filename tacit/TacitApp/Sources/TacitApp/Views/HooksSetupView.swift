import SwiftUI

struct HooksSetupView: View {
    @State private var status: HooksStatusResponse?
    @State private var configJSON: String = ""
    @State private var isLoading = false
    @State private var isInstalling = false
    @State private var isMining = false
    @State private var installMessage: String?
    @State private var miningMessage: String?
    @State private var errorMessage: String?
    @State private var copied = false

    private let backend = BackendService.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                headerSection
                statusSection
                configSection
                miningSection
                recentCapturesSection
            }
            .padding()
        }
        .navigationTitle("Claude Code Hooks")
        .task {
            await loadStatus()
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Live Knowledge Capture")
                .font(.title2)
                .fontWeight(.bold)

            Text("Automatically extract tacit knowledge from your Claude Code sessions in real-time. When a session ends, the hook sends the transcript to Tacit for AI-powered analysis.")
                .font(.body)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Status

    private var statusSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Hook Status")
                        .font(.headline)
                    Spacer()
                    if isLoading {
                        ProgressView()
                            .controlSize(.small)
                    }
                }

                if let status {
                    HStack(spacing: 16) {
                        statusBadge(
                            label: "Script",
                            ok: status.hookScriptExists && status.hookScriptExecutable,
                            detail: status.hookScriptExists ? "Ready" : "Not found"
                        )
                        statusBadge(
                            label: "Installed",
                            ok: status.installedInSettings,
                            detail: status.installedInSettings ? "Active" : "Not installed"
                        )
                    }

                    if !status.installedInSettings {
                        Button {
                            Task { await installHook() }
                        } label: {
                            HStack {
                                if isInstalling {
                                    ProgressView()
                                        .controlSize(.small)
                                }
                                Text("Install Hook")
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isInstalling)
                    }

                    if let installMessage {
                        Text(installMessage)
                            .font(.caption)
                            .foregroundStyle(.green)
                    }
                } else if !isLoading {
                    Text("Unable to check hook status")
                        .foregroundStyle(.secondary)
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
        }
    }

    // MARK: - Config

    private var configSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Configuration")
                        .font(.headline)
                    Spacer()
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(configJSON, forType: .string)
                        copied = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            copied = false
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: copied ? "checkmark" : "doc.on.doc")
                            Text(copied ? "Copied!" : "Copy")
                        }
                    }
                    .buttonStyle(.bordered)
                    .disabled(configJSON.isEmpty)
                }

                Text("Add this to your ~/.claude/settings.json:")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if !configJSON.isEmpty {
                    ScrollView(.horizontal) {
                        Text(configJSON)
                            .font(.system(.caption, design: .monospaced))
                            .padding(8)
                    }
                    .background(Color(nsColor: .textBackgroundColor).opacity(0.5))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .frame(maxHeight: 150)
                }
            }
        }
    }

    // MARK: - Mining

    private var miningSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                Text("Session Mining")
                    .font(.headline)

                Text("Scan all existing Claude Code sessions and extract knowledge before the 30-day cleanup window.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Button {
                        Task { await mineAllSessions() }
                    } label: {
                        HStack {
                            if isMining {
                                ProgressView()
                                    .controlSize(.small)
                            }
                            Text(isMining ? "Mining..." : "Mine All Sessions")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.orange)
                    .disabled(isMining)

                    if let miningMessage {
                        Text(miningMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    // MARK: - Recent Captures

    private var recentCapturesSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                Text("Recent Captures")
                    .font(.headline)

                if let status, !status.recentCaptures.isEmpty {
                    ForEach(status.recentCaptures) { session in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(session.projectPath.isEmpty ? "Unknown project" : session.projectPath)
                                    .font(.caption)
                                    .fontWeight(.medium)
                                    .lineLimit(1)
                                Text("\(session.messageCount) messages")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if session.rulesFound > 0 {
                                Text("\(session.rulesFound) rules")
                                    .font(.caption2)
                                    .fontWeight(.medium)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.blue.opacity(0.15))
                                    .foregroundStyle(.blue)
                                    .clipShape(Capsule())
                            } else {
                                Text("No rules")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .padding(.vertical, 2)
                        Divider()
                    }
                } else {
                    Text("No sessions captured yet. Install the hook or run session mining.")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
        }
    }

    // MARK: - Helpers

    private func statusBadge(label: String, ok: Bool, detail: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundStyle(ok ? .green : .red)
            VStack(alignment: .leading) {
                Text(label)
                    .font(.caption)
                    .fontWeight(.medium)
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Actions

    private func loadStatus() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await backend.getHooksStatus()
            let config = try await backend.getHooksConfig()
            let jsonData = try JSONEncoder().encode(config.config)
            if let jsonObject = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any] {
                let prettyData = try JSONSerialization.data(withJSONObject: jsonObject, options: [.prettyPrinted, .sortedKeys])
                configJSON = String(data: prettyData, encoding: .utf8) ?? ""
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func installHook() async {
        isInstalling = true
        defer { isInstalling = false }
        do {
            let result = try await backend.installHooks()
            installMessage = result.installed ? "Hook installed successfully!" : "Already installed"
            errorMessage = nil
            await loadStatus()
        } catch {
            errorMessage = "Install failed: \(error.localizedDescription)"
        }
    }

    private func mineAllSessions() async {
        isMining = true
        defer { isMining = false }
        do {
            let result = try await backend.mineSessions()
            miningMessage = "Processed \(result.sessionsProcessed) sessions, found \(result.totalRulesFound) rules"
            await loadStatus()
        } catch {
            errorMessage = "Mining failed: \(error.localizedDescription)"
        }
    }
}

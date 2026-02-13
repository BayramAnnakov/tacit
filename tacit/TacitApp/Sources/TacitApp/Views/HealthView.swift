import SwiftUI

struct HealthView: View {
    @State private var health: HealthResponse?
    @State private var isLoading = false
    @State private var errorMessage: String?

    private let backend = BackendService.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let health {
                    statusHeader(health)
                    systemOverview(health)
                    dataBreakdown(health)
                    connectionStatus(health)
                } else if isLoading {
                    ProgressView("Checking system health...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let errorMessage {
                    ContentUnavailableView(
                        "Backend Unreachable",
                        systemImage: "exclamationmark.triangle",
                        description: Text(errorMessage)
                    )
                }
            }
            .padding()
        }
        .navigationTitle("System Health")
        .toolbar {
            ToolbarItem {
                Button {
                    Task { await loadHealth() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
        .task { await loadHealth() }
    }

    private func statusHeader(_ health: HealthResponse) -> some View {
        HStack(spacing: 12) {
            Circle()
                .fill(health.status == "ok" ? .green : .red)
                .frame(width: 12, height: 12)
            Text("Tacit v\(health.version)")
                .font(.title2.weight(.semibold))
            Spacer()
            Text(health.status.uppercased())
                .font(.caption.weight(.bold))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(health.status == "ok" ? Color.green.opacity(0.2) : Color.red.opacity(0.2))
                .clipShape(Capsule())
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func systemOverview(_ health: HealthResponse) -> some View {
        LazyVGrid(columns: [
            GridItem(.flexible()),
            GridItem(.flexible()),
            GridItem(.flexible()),
        ], spacing: 16) {
            statCard("Repositories", "\(health.repositories)", "folder.fill", .teal)
            statCard("Total Rules", "\(health.totalRules)", "book.closed.fill", .blue)
            statCard("Agents", "\(health.agents)", "cpu.fill", .purple)
            statCard("Pending Proposals", "\(health.pendingProposals)", "arrow.up.doc.fill", .orange)
            statCard("Sessions Mined", "\(health.sessionsMined)", "doc.text.magnifyingglass", .indigo)
        }
    }

    private func statCard(_ title: String, _ value: String, _ icon: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)
            Text(value)
                .font(.title.weight(.bold))
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.quaternary.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func dataBreakdown(_ health: HealthResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Rules by Source")
                .font(.headline)

            ForEach(Array(health.rulesBySource.sorted(by: { $0.value > $1.value })), id: \.key) { source, count in
                HStack {
                    Circle()
                        .fill(colorForSource(source))
                        .frame(width: 8, height: 8)
                    Text(source.replacingOccurrences(of: "_", with: " "))
                        .font(.subheadline)
                    Spacer()
                    Text("\(count)")
                        .font(.subheadline.weight(.medium))

                    // Bar visualization
                    let maxCount = health.rulesBySource.values.max() ?? 1
                    RoundedRectangle(cornerRadius: 4)
                        .fill(colorForSource(source).opacity(0.6))
                        .frame(width: CGFloat(count) / CGFloat(maxCount) * 100, height: 8)
                }
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func connectionStatus(_ health: HealthResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Connection Status")
                .font(.headline)

            HStack {
                Image(systemName: health.hookInstalled ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(health.hookInstalled ? .green : .red)
                Text("Claude Code Hook")
                Spacer()
                Text(health.hookInstalled ? "Installed" : "Not Installed")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Image(systemName: health.hookScriptExists ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(health.hookScriptExists ? .green : .red)
                Text("Hook Script")
                Spacer()
                Text(health.hookScriptExists ? "Found" : "Missing")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Image(systemName: backend.isConnected ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(backend.isConnected ? .green : .yellow)
                Text("WebSocket")
                Spacer()
                Text(backend.isConnected ? "Connected" : "Disconnected")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func colorForSource(_ source: String) -> Color {
        switch source {
        case "pr": return .blue
        case "ci_fix": return .red
        case "structure": return .green
        case "docs": return .purple
        case "config": return .orange
        case "conversation": return .cyan
        case "anti_pattern": return .pink
        default: return .gray
        }
    }

    private func loadHealth() async {
        isLoading = true
        defer { isLoading = false }
        do {
            health = try await backend.getHealth()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

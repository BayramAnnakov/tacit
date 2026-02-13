import SwiftUI

struct MetricsView: View {
    let repos: [Repository]
    @State private var selectedRepoId: Int?
    @State private var metricsResponse: OutcomeMetricsResponse?
    @State private var isLoading = false
    @State private var isCollecting = false
    @State private var errorMessage: String?

    private let backend = BackendService.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerSection
            Divider()

            if let metricsResponse {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        summaryCards(metricsResponse)
                        trendSection(metricsResponse)
                        metricsHistory(metricsResponse)
                    }
                    .padding()
                }
            } else if isLoading {
                ProgressView("Loading metrics...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if repos.isEmpty {
                ContentUnavailableView(
                    "No Repositories",
                    systemImage: "chart.line.uptrend.xyaxis",
                    description: Text("Add a repository to start tracking outcome metrics.")
                )
            } else {
                ContentUnavailableView(
                    "Select a Repository",
                    systemImage: "chart.line.uptrend.xyaxis",
                    description: Text("Choose a repository above to view its outcome metrics.")
                )
            }
        }
        .navigationTitle("Outcome Metrics")
        .task {
            if let firstRepo = repos.first {
                selectedRepoId = firstRepo.id
                await loadMetrics(repoId: firstRepo.id)
            }
        }
    }

    private var headerSection: some View {
        HStack {
            Picker("Repository", selection: $selectedRepoId) {
                ForEach(repos) { repo in
                    Text(repo.fullName).tag(Optional(repo.id))
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: 300)
            .onChange(of: selectedRepoId) { _, newValue in
                if let repoId = newValue {
                    Task { await loadMetrics(repoId: repoId) }
                }
            }

            Spacer()

            Button {
                if let repoId = selectedRepoId {
                    Task { await collectNewMetrics(repoId: repoId) }
                }
            } label: {
                Label(isCollecting ? "Collecting..." : "Collect Now", systemImage: "arrow.clockwise")
            }
            .disabled(isCollecting || selectedRepoId == nil)
        }
        .padding()
    }

    private func summaryCards(_ response: OutcomeMetricsResponse) -> some View {
        LazyVGrid(columns: [
            GridItem(.flexible()),
            GridItem(.flexible()),
            GridItem(.flexible()),
            GridItem(.flexible()),
        ], spacing: 16) {
            metricCard(
                title: "Rules Deployed",
                value: "\(response.rulesDeployed)",
                icon: "book.closed.fill",
                color: .blue
            )

            if let latest = response.metrics.first {
                metricCard(
                    title: "Avg Review Rounds",
                    value: String(format: "%.1f", latest.prRevisionRounds),
                    icon: "arrow.triangle.2.circlepath",
                    color: .orange,
                    trend: response.trend["pr_revision_rounds"]
                )
                metricCard(
                    title: "CI Failure Rate",
                    value: String(format: "%.1f%%", latest.ciFailureRate * 100),
                    icon: "xmark.circle",
                    color: .red,
                    trend: response.trend["ci_failure_rate"]
                )
                metricCard(
                    title: "Avg Time to Merge",
                    value: String(format: "%.0fh", latest.timeToMergeHours),
                    icon: "clock.fill",
                    color: .green,
                    trend: response.trend["time_to_merge_hours"]
                )
            }
        }
    }

    private func metricCard(title: String, value: String, icon: String, color: Color, trend: Double? = nil) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(color)
                Spacer()
                if let trend {
                    HStack(spacing: 2) {
                        Image(systemName: trend < 0 ? "arrow.down.right" : "arrow.up.right")
                        Text(String(format: "%.1f%%", abs(trend)))
                    }
                    .font(.caption)
                    .foregroundStyle(trend < 0 ? .green : .red)
                }
            }
            Text(value)
                .font(.title)
                .fontWeight(.bold)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(.quaternary.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func trendSection(_ response: OutcomeMetricsResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Impact Trends")
                .font(.headline)

            if response.trend.isEmpty {
                Text("Collect metrics over multiple weeks to see trends.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(response.trend.sorted(by: { $0.key < $1.key })), id: \.key) { key, value in
                    HStack {
                        Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.subheadline)
                        Spacer()
                        HStack(spacing: 4) {
                            Image(systemName: value < 0 ? "arrow.down" : "arrow.up")
                                .foregroundStyle(value < 0 ? .green : .red)
                            Text(String(format: "%.1f%%", abs(value)))
                                .foregroundStyle(value < 0 ? .green : .red)
                        }
                        .font(.subheadline.weight(.medium))
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func metricsHistory(_ response: OutcomeMetricsResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Weekly History")
                .font(.headline)

            if response.metrics.isEmpty {
                Text("No metrics collected yet. Click 'Collect Now' to start.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(response.metrics) { metric in
                    HStack {
                        Text(metric.weekStart)
                            .font(.caption.monospaced())
                        Spacer()
                        Group {
                            Label(String(format: "%.1f rev", metric.prRevisionRounds), systemImage: "arrow.triangle.2.circlepath")
                            Label(String(format: "%.0f%% CI", metric.ciFailureRate * 100), systemImage: "xmark.circle")
                            Label(String(format: "%.0fh TTM", metric.timeToMergeHours), systemImage: "clock")
                            Label("\(metric.rulesDeployed) rules", systemImage: "book.closed")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                    Divider()
                }
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func loadMetrics(repoId: Int) async {
        isLoading = true
        defer { isLoading = false }
        do {
            metricsResponse = try await backend.getOutcomeMetrics(repoId: repoId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func collectNewMetrics(repoId: Int) async {
        isCollecting = true
        defer { isCollecting = false }
        do {
            _ = try await backend.collectMetrics(repoId: repoId)
            await loadMetrics(repoId: repoId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

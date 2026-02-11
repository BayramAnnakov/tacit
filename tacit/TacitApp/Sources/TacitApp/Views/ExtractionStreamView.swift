import SwiftUI

struct ExtractionStreamView: View {
    @Bindable var vm: ExtractionViewModel
    let repos: [Repository]
    @State private var selectedRepoId: Int?
    @State private var shimmerPhase: CGFloat = 0

    var body: some View {
        VStack(spacing: 0) {
            pipelineProgress
            Divider()
            if vm.events.isEmpty && !vm.isExtracting {
                EmptyStateView(
                    icon: "waveform.path.ecg",
                    title: "Ready to Extract",
                    message: "Select a repository and click Extract to begin discovering team knowledge patterns from PR discussions."
                )
            } else {
                eventStream
            }
            Divider()
            statsBar
        }
        .navigationTitle("Live Extraction")
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
            ToolbarItem(placement: .primaryAction) {
                if vm.isExtracting {
                    Button {
                        vm.stopExtraction()
                    } label: {
                        Label("Stop", systemImage: "stop.fill")
                    }
                    .tint(.red)
                } else {
                    Button {
                        guard let repoId = selectedRepoId else { return }
                        Task { await vm.startExtraction(repoId: repoId) }
                    } label: {
                        Label("Extract", systemImage: "play.fill")
                    }
                    .disabled(selectedRepoId == nil)
                }
            }
            ToolbarItem(placement: .status) {
                if vm.isExtracting {
                    HStack(spacing: 6) {
                        ProgressView()
                            .controlSize(.small)
                        Text("Extracting...")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .onAppear {
            withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                shimmerPhase = 1
            }
        }
    }

    private var pipelineProgress: some View {
        HStack(spacing: 0) {
            ForEach(PipelineStage.allCases, id: \.self) { stage in
                let isActive = vm.isExtracting && stage == vm.currentStage
                let isComplete = stage.rawValue < vm.currentStage.rawValue

                HStack(spacing: 6) {
                    Image(systemName: stage.icon)
                        .font(.caption)
                    Text(stage.label)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity)
                .background {
                    ZStack {
                        if isComplete {
                            Color.green.opacity(0.15)
                        } else if isActive {
                            Color.accentColor.opacity(0.1)
                            shimmerOverlay
                        } else {
                            Color.clear
                        }
                    }
                }
                .foregroundStyle(isComplete ? .green : isActive ? .accentColor : .secondary)

                if stage.rawValue < PipelineStage.allCases.count - 1 {
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundStyle(.quaternary)
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var shimmerOverlay: some View {
        GeometryReader { geo in
            LinearGradient(
                colors: [.clear, .white.opacity(0.15), .clear],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(width: geo.size.width * 0.4)
            .offset(x: shimmerPhase * geo.size.width * 1.4 - geo.size.width * 0.4)
        }
        .clipped()
    }

    private var eventStream: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(vm.events) { event in
                    EventCardView(event: event)
                        .transition(.asymmetric(
                            insertion: .move(edge: .bottom).combined(with: .opacity),
                            removal: .opacity
                        ))
                }
            }
            .padding()
            .animation(.spring(duration: 0.4), value: vm.events.count)
        }
    }

    private var statsBar: some View {
        HStack(spacing: 24) {
            StatCounter(label: "Rules Discovered", value: vm.rulesDiscovered, icon: "sparkles", color: .blue)
            Divider().frame(height: 20)
            StatCounter(label: "Patterns Analyzed", value: vm.patternsAnalyzed, icon: "brain", color: .purple)
            Divider().frame(height: 20)
            StatCounter(label: "Patterns Merged", value: vm.patternsMerged, icon: "arrow.triangle.merge", color: .orange)
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(.bar)
    }
}

struct EventCardView: View {
    let event: ExtractionEvent

    var cardStyle: (Color, String, String) {
        switch event.type {
        case .ruleDiscovered:
            return (.blue, "sparkles", "New Rule")
        case .analyzing:
            return (.gray, "brain", "Analyzing")
        case .patternMerged:
            return (.orange, "arrow.triangle.merge", "Merged")
        case .stageComplete:
            return (.green, "checkmark.circle.fill", "Stage Complete")
        case .error:
            return (.red, "exclamationmark.triangle.fill", "Error")
        case .info:
            return (.secondary, "info.circle", "Info")
        }
    }

    var body: some View {
        let (color, icon, label) = cardStyle

        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(label)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(color)
                        .textCase(.uppercase)
                    Spacer()
                    Text(event.timestamp.formatted(date: .omitted, time: .standard))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }

                if let message = event.data["message"] ?? event.data["rule_text"] ?? event.data["description"] {
                    Text(message)
                        .font(.callout)
                        .lineLimit(3)
                }

                if let category = event.data["category"] {
                    CategoryPill(category: category)
                }
            }
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 10)
                .fill(.background)
                .shadow(color: .black.opacity(0.05), radius: 2, y: 1)
        }
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(color.opacity(event.type == .ruleDiscovered ? 0.4 : 0.15), lineWidth: event.type == .ruleDiscovered ? 2 : 1)
        }
    }
}

import Foundation

enum PipelineStage: Int, CaseIterable {
    case connecting = 0
    case fetching = 1
    case analyzing = 2
    case merging = 3

    var label: String {
        switch self {
        case .connecting: return "Connecting"
        case .fetching: return "Fetching PRs"
        case .analyzing: return "Analyzing"
        case .merging: return "Merging Patterns"
        }
    }

    var icon: String {
        switch self {
        case .connecting: return "network"
        case .fetching: return "arrow.down.doc"
        case .analyzing: return "brain"
        case .merging: return "arrow.triangle.merge"
        }
    }
}

@Observable
final class ExtractionViewModel {
    var events: [ExtractionEvent] = []
    var currentStage: PipelineStage = .connecting
    var isExtracting = false
    var rulesDiscovered = 0
    var patternsAnalyzed = 0
    var patternsMerged = 0

    private let backend = BackendService.shared

    func startExtraction(repoId: Int) async {
        isExtracting = true
        events = []
        rulesDiscovered = 0
        patternsAnalyzed = 0
        patternsMerged = 0
        currentStage = .connecting

        backend.onExtractionEvent = { [weak self] event in
            self?.handleEvent(event)
        }
        backend.connectWebSocket()

        do {
            try await backend.startExtraction(repoId: repoId)
        } catch {
            events.append(ExtractionEvent(
                type: .error,
                data: ["message": error.localizedDescription]
            ))
            isExtracting = false
        }
    }

    func startLocalExtraction(path: String) async {
        isExtracting = true
        events = []
        rulesDiscovered = 0
        patternsAnalyzed = 0
        patternsMerged = 0
        currentStage = .connecting

        backend.onExtractionEvent = { [weak self] event in
            self?.handleEvent(event)
        }
        backend.connectWebSocket()

        do {
            try await backend.startLocalExtraction(projectPath: path)
        } catch {
            events.append(ExtractionEvent(
                type: .error,
                data: ["message": error.localizedDescription]
            ))
            isExtracting = false
        }
    }

    func stopExtraction() {
        backend.disconnectWebSocket()
        backend.onExtractionEvent = nil
        isExtracting = false
    }

    private func handleEvent(_ event: ExtractionEvent) {
        events.insert(event, at: 0)

        // Map backend stage strings to frontend PipelineStage
        if let stage = event.data["stage"] {
            switch stage {
            case "scanning": currentStage = .fetching
            case "analyzing": currentStage = .analyzing
            case "synthesizing": currentStage = .merging
            default: break
            }
        }

        switch event.type {
        case .ruleDiscovered:
            rulesDiscovered += 1
        case .analyzing:
            patternsAnalyzed += 1
        case .patternMerged:
            patternsMerged += 1
        case .stageComplete:
            if event.data["stage"] == "done" {
                isExtracting = false
                backend.disconnectWebSocket()
            }
        case .error:
            break
        case .info:
            break
        }
    }
}

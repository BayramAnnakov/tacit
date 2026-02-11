import Foundation

@Observable
final class ProcessManager {
    static let shared = ProcessManager()

    var isBackendRunning = false
    var backendOutput: [String] = []

    private var process: Process?

    private init() {}

    func launchBackend() {
        guard !isBackendRunning else { return }

        let process = Process()
        let pipe = Pipe()

        let tacitDir = findTacitBackendDir()

        let venvPython = "\(tacitDir)/.venv/bin/python"
        let systemPython = "/usr/bin/env"

        if FileManager.default.fileExists(atPath: venvPython) {
            process.executableURL = URL(fileURLWithPath: venvPython)
            process.arguments = ["-m", "uvicorn", "tacit.api:app", "--host", "0.0.0.0", "--port", "8000"]
        } else {
            process.executableURL = URL(fileURLWithPath: systemPython)
            process.arguments = ["python3", "-m", "uvicorn", "tacit.api:app", "--host", "0.0.0.0", "--port", "8000"]
        }

        process.currentDirectoryURL = URL(fileURLWithPath: tacitDir)
        process.standardOutput = pipe
        process.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let line = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.backendOutput.append(line)
                if self?.backendOutput.count ?? 0 > 500 {
                    self?.backendOutput.removeFirst()
                }
            }
        }

        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.isBackendRunning = false
            }
        }

        do {
            try process.run()
            self.process = process
            isBackendRunning = true
        } catch {
            backendOutput.append("Failed to launch backend: \(error.localizedDescription)")
        }
    }

    func stopBackend() {
        process?.terminate()
        process = nil
        isBackendRunning = false
    }

    private func findTacitBackendDir() -> String {
        let bundle = Bundle.main.bundlePath
        let candidates = [
            URL(fileURLWithPath: bundle).deletingLastPathComponent().appendingPathComponent("tacit").path,
            URL(fileURLWithPath: bundle).deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("tacit").path,
            FileManager.default.currentDirectoryPath + "/tacit",
            NSHomeDirectory() + "/GH/opus-4-6-hack/tacit"
        ]
        for candidate in candidates {
            if FileManager.default.fileExists(atPath: candidate + "/tacit") {
                return candidate
            }
        }
        return candidates.last!
    }
}

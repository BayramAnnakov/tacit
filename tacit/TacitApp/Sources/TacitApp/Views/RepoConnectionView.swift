import SwiftUI

struct RepoConnectionView: View {
    @Bindable var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var repoURL = ""
    @State private var githubToken = ""
    @State private var isConnecting = false

    var body: some View {
        VStack(spacing: 20) {
            header

            Form {
                Section {
                    TextField("Repository URL", text: $repoURL, prompt: Text("https://github.com/org/repo"))
                }

                Section {
                    SecureField("GitHub Token", text: $githubToken, prompt: Text("ghp_..."))
                } footer: {
                    Text("Required for private repositories. Generate at GitHub Settings > Developer settings > Personal access tokens.")
                }
            }
            .formStyle(.grouped)
            .scrollDisabled(true)
            .frame(height: 180)

            HStack {
                Button("Cancel", role: .cancel) {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)

                Spacer()

                Button {
                    Task {
                        isConnecting = true
                        let countBefore = appVM.repos.count
                        await appVM.addRepo(
                            url: repoURL,
                            token: githubToken.isEmpty ? nil : githubToken
                        )
                        isConnecting = false
                        if appVM.repos.count > countBefore {
                            dismiss()
                        }
                    }
                } label: {
                    if isConnecting {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text("Connect")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(repoURL.isEmpty || isConnecting)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal)
        }
        .padding(.vertical, 20)
        .frame(width: 460)
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "link.circle.fill")
                .font(.system(size: 40))
                .foregroundStyle(.blue)
            Text("Connect Repository")
                .font(.title3)
                .fontWeight(.semibold)
            Text("Enter the GitHub repository URL to begin extracting team knowledge.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
        }
    }
}

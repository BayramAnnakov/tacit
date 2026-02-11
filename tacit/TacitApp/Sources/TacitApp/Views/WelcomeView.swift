import SwiftUI

struct WelcomeView: View {
    @Bindable var appVM: AppViewModel

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 16) {
                Image(systemName: "brain.head.profile.fill")
                    .font(.system(size: 64))
                    .foregroundStyle(.blue.gradient)

                Text("Tacit")
                    .font(.largeTitle)
                    .fontWeight(.bold)

                Text("Team Knowledge Engine")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 12) {
                FeatureRow(
                    icon: "arrow.triangle.pull",
                    color: .blue,
                    title: "Extract from PRs",
                    subtitle: "Discover team patterns from pull request discussions"
                )
                FeatureRow(
                    icon: "bubble.left.and.bubble.right.fill",
                    color: .purple,
                    title: "Learn from Conversations",
                    subtitle: "Mine Claude Code sessions for coding decisions"
                )
                FeatureRow(
                    icon: "doc.text.fill",
                    color: .green,
                    title: "Generate CLAUDE.md",
                    subtitle: "Auto-generate project instructions from team knowledge"
                )
                FeatureRow(
                    icon: "person.3.fill",
                    color: .orange,
                    title: "Team Proposals",
                    subtitle: "Review and vote on discovered knowledge rules"
                )
            }
            .frame(maxWidth: 400)

            Button {
                appVM.showAddRepoSheet = true
            } label: {
                Label("Connect Your First Repository", systemImage: "plus.circle.fill")
                    .font(.headline)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct FeatureRow: View {
    let icon: String
    let color: Color
    let title: String
    let subtitle: String

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)
                .frame(width: 36)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 16)
        .background(.quaternary.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

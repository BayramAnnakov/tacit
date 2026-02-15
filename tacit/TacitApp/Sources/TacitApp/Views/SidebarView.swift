import SwiftUI

struct SidebarView: View {
    @Bindable var appVM: AppViewModel
    var knowledgeCount: Int
    var proposalCount: Int

    var body: some View {
        List(selection: $appVM.selectedSidebarItem) {
            Section("Knowledge") {
                Label {
                    HStack {
                        Text("Team Knowledge")
                        Spacer()
                        if knowledgeCount > 0 {
                            Text("\(knowledgeCount)")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.tertiary)
                                .clipShape(Capsule())
                        }
                    }
                } icon: {
                    Image(systemName: "book.closed.fill")
                        .foregroundStyle(.blue)
                }
                .tag(SidebarItem.teamKnowledge)

                Label {
                    Text("My Discoveries")
                } icon: {
                    Image(systemName: "lightbulb.fill")
                        .foregroundStyle(.yellow)
                }
                .tag(SidebarItem.myDiscoveries)

                Label {
                    HStack {
                        Text("Proposals")
                        Spacer()
                        if proposalCount > 0 {
                            Text("\(proposalCount)")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.orange.opacity(0.2))
                                .foregroundStyle(.orange)
                                .clipShape(Capsule())
                        }
                    }
                } icon: {
                    Image(systemName: "arrow.up.doc.fill")
                        .foregroundStyle(.orange)
                }
                .tag(SidebarItem.proposals)

                Label {
                    Text("CLAUDE.md")
                } icon: {
                    Image(systemName: "doc.text.fill")
                        .foregroundStyle(.purple)
                }
                .tag(SidebarItem.claudeMD)

                Label {
                    Text(".claude/rules/")
                } icon: {
                    Image(systemName: "folder.badge.gearshape")
                        .foregroundStyle(.teal)
                }
                .tag(SidebarItem.modularRules)

                Label {
                    Text("Org Patterns")
                } icon: {
                    Image(systemName: "globe.americas.fill")
                        .foregroundStyle(.indigo)
                }
                .tag(SidebarItem.orgPatterns)
            }

            Section("Live") {
                Label {
                    Text("Extraction")
                } icon: {
                    Image(systemName: "waveform.path.ecg")
                        .foregroundStyle(.green)
                }
                .tag(SidebarItem.extraction)

                Label {
                    Text("Hooks")
                } icon: {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                        .foregroundStyle(.cyan)
                }
                .tag(SidebarItem.hooks)

                Label {
                    Text("Onboarding")
                } icon: {
                    Image(systemName: "person.badge.plus")
                        .foregroundStyle(.orange)
                }
                .tag(SidebarItem.onboarding)
            }

            Section("Insights") {
                Label {
                    Text("Metrics")
                } icon: {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .foregroundStyle(.mint)
                }
                .tag(SidebarItem.metrics)

                Label {
                    Text("Health")
                } icon: {
                    Image(systemName: "heart.text.square.fill")
                        .foregroundStyle(.pink)
                }
                .tag(SidebarItem.health)
            }

            Section("Repositories") {
                ForEach(appVM.repos) { repo in
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(repo.fullName)
                        }
                    } icon: {
                        Image(systemName: "folder.fill")
                            .foregroundStyle(.teal)
                    }
                    .tag(SidebarItem.repo(repo))
                }

                Button {
                    appVM.showAddRepoSheet = true
                } label: {
                    Label("Add Repository", systemImage: "plus.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Tacit")
        .toolbar {
            ToolbarItem {
                Button {
                    appVM.showAddRepoSheet = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
    }
}

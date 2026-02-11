import SwiftUI

struct KnowledgeBrowserView: View {
    @Bindable var vm: KnowledgeViewModel
    var repoId: Int?

    var body: some View {
        VStack(spacing: 0) {
            searchBar
            Divider()
            rulesList
        }
        .navigationTitle(repoId != nil ? "Repository Knowledge" : "Team Knowledge")
        .task {
            await vm.loadRules(repoId: repoId)
        }
        .onChange(of: vm.searchText) { _, _ in
            Task { await vm.loadRules(repoId: repoId) }
        }
        .onChange(of: vm.selectedCategory) { _, _ in
            Task { await vm.loadRules(repoId: repoId) }
        }
    }

    private var searchBar: some View {
        VStack(spacing: 8) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search knowledge...", text: $vm.searchText)
                    .textFieldStyle(.plain)
                if !vm.searchText.isEmpty {
                    Button {
                        vm.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(8)
            .background(.quaternary)
            .clipShape(RoundedRectangle(cornerRadius: 8))

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(vm.categories, id: \.self) { cat in
                        let label = cat.isEmpty ? "All" : cat
                        Button {
                            vm.selectedCategory = cat
                        } label: {
                            Text(label)
                                .font(.caption)
                                .fontWeight(vm.selectedCategory == cat ? .semibold : .regular)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(vm.selectedCategory == cat ? Color.accentColor.opacity(0.2) : Color.clear)
                                .foregroundStyle(vm.selectedCategory == cat ? Color.accentColor : .secondary)
                                .clipShape(Capsule())
                                .overlay(Capsule().stroke(vm.selectedCategory == cat ? Color.accentColor.opacity(0.3) : Color.secondary.opacity(0.2), lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding()
    }

    private var rulesList: some View {
        Group {
            if vm.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.rules.isEmpty {
                EmptyStateView(
                    icon: "book.closed",
                    title: "No Knowledge Rules",
                    message: "Connect a repository and run extraction to discover team knowledge patterns."
                )
            } else {
                List(vm.rules, selection: $vm.selectedRule) { rule in
                    RuleCardView(rule: rule)
                        .tag(rule)
                }
                .listStyle(.inset)
            }
        }
    }
}

struct RuleCardView: View {
    let rule: KnowledgeRule

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(rule.ruleText)
                .font(.callout)
                .lineLimit(3)

            HStack(spacing: 6) {
                CategoryPill(category: rule.category)
                ConfidenceBadge(confidence: rule.confidence)
                SourceBadge(sourceType: rule.sourceType)
                Spacer()
            }
        }
        .padding(.vertical, 4)
    }
}

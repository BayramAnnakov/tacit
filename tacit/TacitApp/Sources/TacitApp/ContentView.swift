import SwiftUI

struct ContentView: View {
    @State private var appVM = AppViewModel()
    @State private var knowledgeVM = KnowledgeViewModel()
    @State private var proposalVM = ProposalViewModel()
    @State private var extractionVM = ExtractionViewModel()
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        mainContent
            .frame(minWidth: 1000, minHeight: 600)
            .sheet(isPresented: $appVM.showAddRepoSheet) {
                RepoConnectionView(appVM: appVM)
            }
            .alert("Error", isPresented: $appVM.showError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(appVM.errorMessage ?? "An unknown error occurred.")
            }
            .task {
                await appVM.loadRepos()
                await knowledgeVM.loadRules()
                await proposalVM.loadProposals()
            }
    }

    private var mainContent: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            SidebarView(
                appVM: appVM,
                knowledgeCount: knowledgeVM.rules.count,
                proposalCount: proposalVM.proposals.count
            )
            .navigationSplitViewColumnWidth(min: 200, ideal: 240, max: 300)
        } content: {
            contentColumn
                .navigationSplitViewColumnWidth(min: 280, ideal: 340, max: 500)
        } detail: {
            detailColumn
                .navigationSplitViewColumnWidth(min: 400, ideal: 500)
        }
        .navigationSplitViewStyle(.balanced)
    }

    @ViewBuilder
    private var contentColumn: some View {
        switch appVM.selectedSidebarItem {
        case .teamKnowledge:
            KnowledgeBrowserView(vm: knowledgeVM)
        case .myDiscoveries:
            MyDiscoveriesView(extractionVM: extractionVM)
        case .proposals:
            ProposalListView(vm: proposalVM)
        case .claudeMD:
            ClaudeMDEditorView(repos: appVM.repos)
        case .extraction:
            ExtractionStreamView(vm: extractionVM, repos: appVM.repos)
        case .repo(let repo):
            KnowledgeBrowserView(vm: knowledgeVM, repoId: repo.id)
        case nil:
            Text("Select an item")
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var detailColumn: some View {
        switch appVM.selectedSidebarItem {
        case .teamKnowledge, .repo:
            ruleDetailView
        case .proposals:
            proposalDetailView
        default:
            defaultDetailView
        }
    }

    @ViewBuilder
    private var ruleDetailView: some View {
        if let rule = knowledgeVM.selectedRule {
            KnowledgeRuleDetailView(rule: rule, vm: knowledgeVM)
        } else {
            ContentUnavailableView(
                "No Rule Selected",
                systemImage: "book.closed",
                description: Text("Select a knowledge rule to view its details and decision trail.")
            )
        }
    }

    @ViewBuilder
    private var proposalDetailView: some View {
        if let proposal = proposalVM.selectedProposal {
            ProposalReviewView(proposal: proposal, vm: proposalVM)
        } else {
            ContentUnavailableView(
                "No Proposal Selected",
                systemImage: "arrow.up.doc",
                description: Text("Select a proposal to review.")
            )
        }
    }

    @ViewBuilder
    private var defaultDetailView: some View {
        if appVM.repos.isEmpty {
            WelcomeView(appVM: appVM)
        } else {
            ContentUnavailableView(
                "Select a Section",
                systemImage: "sidebar.left",
                description: Text("Choose a section from the sidebar to get started.")
            )
        }
    }
}

---
description: SwiftUI macOS frontend -- views, services, view models
paths:
  - "tacit/TacitApp/**/*.swift"
---

- SwiftUI 3-column `NavigationSplitView`: sidebar -> content -> detail
- `BackendService` singleton for REST + WebSocket communication at `localhost:8000`
- No external Swift dependencies -- pure SwiftUI + Foundation

### Views
- `SidebarView` -- navigation with section groups
- `KnowledgeBrowserView` -- browse/search/filter rules with feedback
- `ProposalListView` / `ProposalReviewView` -- proposal management
- `ClaudeMDEditorView` -- diff mode + PR creation
- `ExtractionStreamView` -- live extraction progress via WebSocket
- `HooksSetupView` -- hook install, status, and session mining
- `MetricsView` -- outcome metrics dashboard
- `HealthView` -- system health monitoring
- `OrgPatternsView` -- cross-repo pattern detection
- `MyDiscoveriesView` -- personal extraction history

### View Models
- `AppViewModel` -- app-wide state, repo selection
- `KnowledgeViewModel` -- knowledge rule list, filtering, feedback
- `ProposalViewModel` -- proposal list, review actions
- `ExtractionViewModel` -- extraction progress, WebSocket events

### Patterns
- Use `@Observable` for view models
- Use `@State` for view-local state
- Use `Task { }` blocks for async calls from SwiftUI views
- Handle WebSocket reconnection in `BackendService`

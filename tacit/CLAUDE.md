# Tacit — Team Knowledge Extraction

Extract tacit knowledge from GitHub PRs and Claude Code conversations, surface it for team review, and generate CLAUDE.md files.

## Architecture

**Backend** (Python 3.12+, FastAPI)
- `backend/main.py` — REST API + WebSocket server (port 8000)
- `backend/pipeline.py` — 4-pass extraction pipeline using Claude Agent SDK
- `backend/agents.py` — 5 agent definitions (pr-scanner, thread-analyzer, synthesizer, generator, local-extractor)
- `backend/tools.py` — MCP tools (GitHub API, log reader, knowledge storage)
- `backend/database.py` — SQLite via aiosqlite (tacit.db)
- `backend/models.py` — Pydantic models
- `backend/proposals.py` — Proposal approve/reject logic
- `backend/config.py` — Settings from .env
- `backend/prompts/*.md` — Agent system prompt templates

**Frontend** (Swift 5.9, SwiftUI, macOS 14+)
- `TacitApp/Sources/TacitApp/` — macOS app
- `Services/BackendService.swift` — HTTP + WebSocket client
- `ViewModels/` — AppViewModel, ExtractionViewModel, KnowledgeViewModel, ProposalViewModel
- `Views/` — ExtractionStreamView, KnowledgeBrowserView, ProposalListView, MyDiscoveriesView, ClaudeMDEditorView
- `Models/` — Repository, KnowledgeRule, Proposal, ExtractionEvent, DecisionTrail

## Dev Commands

```bash
# Backend
cd tacit/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py  # starts on localhost:8000

# Frontend
cd tacit/TacitApp
swift build
swift run TacitApp  # or open in Xcode

# Reset DB (after schema changes)
rm backend/tacit.db  # auto-recreated on startup
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/health | Health check |
| POST | /api/repos | Connect a repository |
| GET | /api/repos | List repositories |
| POST | /api/extract/{repo_id} | Start extraction (body: {github_token}) |
| GET | /api/knowledge?q=&category=&repo_id= | List/search knowledge rules |
| GET | /api/knowledge/{id} | Rule detail + decision trail |
| POST | /api/proposals | Create proposal |
| GET | /api/proposals?status= | List proposals |
| PUT | /api/proposals/{id} | Approve/reject proposal |
| GET | /api/claude-md/{repo_id} | Generate CLAUDE.md |
| POST | /api/local-extract | Extract from local logs |
| WS | /ws | Real-time extraction events |

## WebSocket Event Wire Format

```json
{"type": "<frontend_event_type>", "data": {"message": "...", ...}, "timestamp": "ISO8601"}
```

Frontend event types: `rule_discovered`, `analyzing`, `pattern_merged`, `stage_complete`, `error`, `info`

## Extraction Pipeline

1. **PR Scanner** (Sonnet) — Identifies knowledge-rich PRs
2. **Thread Analyzer** (Opus) — Extracts rules from PR discussions
3. **Synthesizer** (Opus) — Merges/deduplicates rules
4. **Generator** (Opus) — Generates CLAUDE.md from knowledge base

## Conventions

- Backend: snake_case, async/await throughout, aiosqlite for DB
- Frontend: Swift naming conventions, @Observable for state, CodingKeys for snake_case ↔ camelCase
- All data values in WebSocket events must be stringified for Swift `[String: String]`
- Environment: .env for secrets (ANTHROPIC_API_KEY, GITHUB_TOKEN)

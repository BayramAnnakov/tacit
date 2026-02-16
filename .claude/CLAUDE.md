# Tacit

Continuous team knowledge extraction system. Extracts tacit conventions from GitHub PRs, CI failures, documentation, code configs, and Claude Code session transcripts, then generates CLAUDE.md and `.claude/rules/` files.

## Quick Start

### Backend

```bash
cd tacit/backend
source venv/bin/activate
python main.py
# -> http://127.0.0.1:8000
```

Requires `.env` in `tacit/backend/` with `ANTHROPIC_API_KEY` and `GITHUB_TOKEN`.

### Frontend (macOS)

```bash
cd tacit/TacitApp
swift build && swift run TacitApp
# Or: open Package.swift  (Xcode)
```

### CLI Tool

```bash
cd tacit/backend && source venv/bin/activate
python __main__.py owner/repo                  # Extract + print CLAUDE.md
python __main__.py owner/repo --modular        # Extract + print .claude/rules/
python __main__.py owner/repo --skip-extract   # Reuse existing DB
python __main__.py owner/repo --skip-extract --summary  # Quick stats + top rules
```

### Eval

```bash
cd tacit/backend
source venv/bin/activate
python eval_extract.py               # v1: extraction quality vs ground truth
python eval_v2.py                    # v2: 8 capability evals
python eval_v2.py --skip-extraction  # v2: reuse existing DB
```

## Architecture

Two components: Python FastAPI backend + SwiftUI macOS frontend, connected via REST + WebSocket.

- **16 agents** defined in `agents.py` using `AgentDefinition` dataclass
- **20 MCP tools** defined in `tools.py` and `db_tools.py` using `@tool` decorator
- **4-phase extraction pipeline** in `pipeline.py`
- **SQLite database** via `aiosqlite` (WAL mode)

See `.claude/rules/` for detailed conventions on each subsystem.

## Key Files

| File | Purpose |
|------|---------|
| `tacit/backend/pipeline.py` | Extraction orchestrator (4-phase + session mining + incremental) |
| `tacit/backend/agents.py` | Agent definitions (16 agents) |
| `tacit/backend/tools.py` | MCP tools (20 tools, including db_tools.py) |
| `tacit/backend/db_tools.py` | Read-only database introspection tools (4 tools) |
| `tacit/backend/database.py` | SQLite schema and CRUD |
| `tacit/backend/main.py` | FastAPI app (REST + WebSocket + webhook) |
| `tacit/backend/__main__.py` | CLI tool (`python __main__.py owner/repo`) |
| `tacit/backend/__main__.py` | CLI tool (`python __main__.py owner/repo --summary`) |
| `tacit/backend/eval_v2.py` | Eval suite (8 evals, 83% overall) |
| `tacit/backend/prompts/` | Agent prompt files (16 prompts) |
| `tacit/TacitApp/` | SwiftUI macOS frontend |

## Issue Tracking

Use **Beads** (`bd` CLI) for git-native issue tracking:
```bash
bd ready          # Find available work
bd create "..."   # Create issue
bd close <id>     # Complete work
bd sync           # Sync with git
```

## Session Completion

Push to remote when ending a work session. Work is NOT complete until `git push` succeeds.

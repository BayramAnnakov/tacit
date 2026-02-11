# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tacit** extracts tacit team knowledge from GitHub PRs and Claude Code conversations, then generates CLAUDE.md files. It uses a multi-source extraction pipeline powered by Claude Agent SDK agents.

## Quick Start

### Backend

```bash
cd tacit/backend
source venv/bin/activate
python main.py
# → http://127.0.0.1:8000
```

Requires `.env` in `tacit/backend/` with `ANTHROPIC_API_KEY` and `GITHUB_TOKEN`.

### Frontend (macOS)

```bash
cd tacit/TacitApp
swift build && swift run TacitApp
# Or: open Package.swift  (Xcode)
```

### Eval

```bash
cd tacit/backend
source venv/bin/activate
python eval_extract.py
# Runs extraction on test repos, compares against ground truth CLAUDE.md files
```

## Architecture

Two components: Python FastAPI backend + SwiftUI macOS frontend, connected via REST + WebSocket.

### Extraction Pipeline (4 phases in `pipeline.py`)

**Phase 1 — Parallel analysis** (3 concurrent tasks):
- `structural-analyzer` (Sonnet): repo tree, commit messages, branch rulesets
- `docs-analyzer` (Sonnet): CONTRIBUTING.md, README, existing CLAUDE.md/AGENTS.md
- `ci-failure-miner` (Opus): CI failure→fix diffs to infer implicit conventions

**Phase 2 — Sequential PR analysis**:
- `pr-scanner` (Sonnet): identifies knowledge-rich PRs (first-timers, CHANGES_REQUESTED)
- `thread-analyzer` (Opus): deep-analyzes each PR's discussion threads

**Phase 3** — Await parallel tasks

**Phase 4 — Synthesis**:
- `synthesizer` (Opus): cross-source dedup, confidence boosting, removes generic rules
- `generator` (Opus): produces structured CLAUDE.md output (called on-demand via API)

### Agent System

Agents are defined in `agents.py` using `AgentDefinition` dataclass. Each agent has:
- A prompt file in `prompts/<name>.md`
- A model assignment (sonnet or opus)
- A list of MCP tool names

Tools are defined in `tools.py` using the `@tool` decorator from `claude_agent_sdk`. The `create_tacit_tools_server()` function creates an in-process MCP server. Agents are run via `ClaudeSDKClient` with `ClaudeAgentOptions`.

### Database

SQLite via `aiosqlite` (WAL mode). Schema is in `database.py` as `SCHEMA` constant. Key tables: `repositories`, `knowledge_rules`, `proposals`, `extraction_runs`, `decision_trail`.

To reset: delete `tacit/backend/tacit.db` and restart (auto-recreates with seed data).

### Frontend

SwiftUI 3-column `NavigationSplitView`. Views connect to backend via `BackendService` (REST + WebSocket at `localhost:8000`). No external Swift dependencies.

## Adding New Agents

1. Create prompt: `tacit/backend/prompts/<agent_name>.md`
2. Add `AgentDefinition` in `agents.py` → `get_agent_definitions()` dict
3. Add any new tools in `tools.py` with `@tool` decorator
4. Register tool names in `_RAW_TOOL_NAMES` list in `tools.py`
5. Wire into pipeline in `pipeline.py`

## Adding New MCP Tools

1. Define function with `@tool(name=..., description=...)` in `tools.py`
2. Parameters come from the function signature; use `repo: str` and `github_token: str` for GitHub tools
3. Add the tool name string to `_RAW_TOOL_NAMES`
4. Reference the tool name in the agent's `tools` list in `agents.py`

## Key Files

| File | Purpose |
|------|---------|
| `tacit/backend/pipeline.py` | Extraction orchestrator (4-phase async pipeline) |
| `tacit/backend/agents.py` | Agent definitions (model, tools, prompt mapping) |
| `tacit/backend/tools.py` | MCP tools (GitHub API, knowledge CRUD) |
| `tacit/backend/database.py` | SQLite schema, CRUD, seed data |
| `tacit/backend/main.py` | FastAPI app (REST + WebSocket endpoints) |
| `tacit/backend/models.py` | Pydantic models (`KnowledgeRule`, `ExtractionEvent`) |
| `tacit/backend/prompts/` | Agent prompt markdown files (8 prompts) |
| `tacit/backend/eval_extract.py` | Eval runner: extract → compare against ground truth |
| `tacit/backend/generated_claude_md/` | Eval outputs (generated + real CLAUDE.md pairs) |

## Source Types and Confidence

Rules are stored with `source_type`: `pr`, `conversation`, `structure`, `docs`, `ci_fix`.

Authority hierarchy (when rules conflict): `ci_fix` > `structure`/`docs` > `pr` > `conversation`.

Cross-source boosting: rule found in 2+ sources gets +0.10 confidence; `ci_fix` AND `pr` → 0.95.

## Issue Tracking

This project uses **Beads** (`bd` CLI) for git-native issue tracking:
```bash
bd ready          # Find available work
bd create "..."   # Create issue
bd close <id>     # Complete work
bd sync           # Sync with git
```

## Session Completion

When ending a work session, push to remote. Work is NOT complete until `git push` succeeds.

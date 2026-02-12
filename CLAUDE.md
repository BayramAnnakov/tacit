# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tacit** is a continuous team knowledge extraction system. It extracts tacit conventions from GitHub PRs, CI failures, documentation, and code configs, then generates CLAUDE.md files. It uses a multi-source extraction pipeline powered by Claude Agent SDK agents, with webhook-driven continuous learning and PR validation.

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

**Phase 1 — Parallel analysis** (4 concurrent tasks):
- `structural-analyzer` (Sonnet): repo tree, commit messages, branch rulesets
- `docs-analyzer` (Sonnet): CONTRIBUTING.md, README, existing CLAUDE.md/AGENTS.md
- `ci-failure-miner` (Opus): CI failure→fix diffs to infer implicit conventions
- `code-analyzer` (Sonnet): test configs, linter configs, CI workflows, package configs

**Phase 2 — Parallel PR analysis** (3 concurrent via `asyncio.Semaphore`):
- `pr-scanner` (Sonnet): identifies knowledge-rich PRs (first-timers, CHANGES_REQUESTED)
- `thread-analyzer` (Opus): deep-analyzes each PR's discussion threads (3 at a time)

**Phase 3** — Await Phase 1 parallel tasks

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

SQLite via `aiosqlite` (WAL mode). Schema is in `database.py` as `SCHEMA` constant. Key tables: `repositories`, `knowledge_rules` (with `feedback_score`), `proposals`, `extraction_runs`, `decision_trail`.

To reset: delete `tacit/backend/tacit.db` and restart (auto-recreates with seed data).

### Frontend

SwiftUI 3-column `NavigationSplitView`. Views connect to backend via `BackendService` (REST + WebSocket at `localhost:8000`). No external Swift dependencies. Supports: knowledge browsing with feedback, CLAUDE.md diff mode + PR creation, org-wide cross-repo pattern detection.

## API Endpoints

### Core
- `POST /api/repos` — Connect a GitHub repository
- `GET /api/repos` — List connected repositories
- `POST /api/extract/{repo_id}` — Start knowledge extraction
- `POST /api/local-extract` — Extract from local conversation logs

### Knowledge
- `GET /api/knowledge` — List rules (filter by category, repo_id, search)
- `GET /api/knowledge/{id}` — Rule detail with decision trail
- `POST /api/knowledge/{id}/feedback` — Upvote/downvote a rule (`{vote: "up"|"down"}`)
- `GET /api/stats/source-quality` — Aggregated quality stats by source type
- `GET /api/knowledge/cross-repo` — Cross-repo shared patterns

### CLAUDE.md
- `GET /api/claude-md/{repo_id}` — Generate CLAUDE.md from knowledge base
- `GET /api/claude-md/{repo_id}/diff` — Diff existing vs generated CLAUDE.md
- `POST /api/claude-md/{repo_id}/create-pr` — Create GitHub PR with CLAUDE.md

### PR Validation
- `POST /api/validate-pr` — Validate PR against knowledge rules
- `POST /api/validate-pr/post-review` — Post review comments on GitHub PR

### Automation
- `POST /api/webhook/github` — GitHub webhook for continuous learning (merged PRs)

### Proposals
- `POST /api/proposals` — Create proposal
- `GET /api/proposals` — List proposals
- `PUT /api/proposals/{id}` — Approve/reject proposal

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
| `tacit/backend/tools.py` | MCP tools (GitHub API, knowledge CRUD, PR diff) |
| `tacit/backend/database.py` | SQLite schema, CRUD, feedback scoring |
| `tacit/backend/main.py` | FastAPI app (REST + WebSocket + webhook endpoints) |
| `tacit/backend/models.py` | Pydantic models (`KnowledgeRule`, `PRValidationResult`, etc.) |
| `tacit/backend/prompts/` | Agent prompt markdown files (10 prompts) |
| `tacit/backend/templates/` | GitHub Action template for PR validation |
| `tacit/backend/samples/` | Sample webhook payload for testing |
| `tacit/backend/eval_extract.py` | Eval runner: extract → compare against ground truth |
| `tacit/backend/generated_claude_md/` | Eval outputs (generated + real CLAUDE.md pairs) |

## Source Types and Confidence

Rules are stored with `source_type`: `pr`, `conversation`, `structure`, `docs`, `ci_fix`, `config`.

Authority hierarchy (when rules conflict): `ci_fix` > `structure`/`docs` > `pr` > `conversation`.

Cross-source boosting: rule found in 2+ sources gets +0.10 confidence; `ci_fix` AND `pr` → 0.95.

User feedback (`feedback_score`) tracks upvotes/downvotes per rule. Source quality stats available via `/api/stats/source-quality`.

## Webhook Setup

To enable continuous learning from merged PRs:

1. In GitHub repo settings → Webhooks → Add webhook
2. Payload URL: `https://your-tacit-host/api/webhook/github`
3. Content type: `application/json`
4. Events: Pull requests only
5. (Optional) Set `WEBHOOK_SECRET` in `.env` for HMAC verification

## GitHub Action for PR Validation

Copy `tacit/backend/templates/tacit-validate.yml` to `.github/workflows/` in target repos. Set `TACIT_URL` and `GITHUB_TOKEN` as repository secrets.

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

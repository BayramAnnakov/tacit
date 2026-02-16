# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tacit** is a continuous team knowledge extraction system. It extracts tacit conventions from GitHub PRs, CI failures, documentation, code configs, and Claude Code session transcripts, then generates CLAUDE.md files. It uses a multi-source extraction pipeline powered by Claude Agent SDK agents, with webhook-driven continuous learning, real-time hook capture, session transcript mining, and PR validation.

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
python eval_extract.py            # v1: extraction quality vs ground truth
python eval_v2.py                 # v2: 8 capability evals, 83% overall (anti-patterns, provenance, path scoping, modular rules, incremental, metrics, domain knowledge, ground truth recall)
python eval_v2.py --skip-extraction  # v2: reuse existing DB, run evals only
```

## Architecture

Two components: Python FastAPI backend + SwiftUI macOS frontend, connected via REST + WebSocket.

### Extraction Pipeline (4 phases in `pipeline.py`)

**Phase 1 — Parallel analysis** (5 concurrent tasks):
- `structural-analyzer` (Sonnet): repo tree, commit messages, branch rulesets
- `docs-analyzer` (Sonnet): CONTRIBUTING.md, README, existing CLAUDE.md/AGENTS.md
- `ci-failure-miner` (Opus): CI failure→fix diffs to infer implicit conventions
- `code-analyzer` (Sonnet): test configs, linter configs, CI workflows, package configs
- `anti-pattern-miner` (Opus): CHANGES_REQUESTED PR reviews → "Do Not" rules with provenance

**Phase 2 — Parallel PR analysis** (3 concurrent via `asyncio.Semaphore`):
- `pr-scanner` (Sonnet): identifies knowledge-rich PRs (first-timers, CHANGES_REQUESTED)
- `thread-analyzer` (Opus): deep-analyzes each PR's discussion threads (3 at a time), captures provenance and applicable paths

**Phase 3** — Await Phase 1 parallel tasks

**Phase 4 — Synthesis + Cleanup**:
- `synthesizer` (Opus): cross-source dedup, confidence boosting, removes generic rules
- Post-synthesis programmatic filter: removes rules matching 28 known generic patterns (3-layer filtering)
- `generator` (Opus): produces structured CLAUDE.md output (called on-demand via API)
- `modular-generator` (Opus): produces `.claude/rules/` directory with path-scoped YAML frontmatter files

### Session Mining Pipeline (`mine_session()` / `mine_all_sessions()` in `pipeline.py`)

Scans `~/.claude/projects/` for JSONL transcripts, reads user/assistant messages, and sends them to the `session-analyzer` agent for knowledge extraction. Tracks processed files in `mined_sessions` table to avoid re-mining. Processes newest transcripts first.

### Claude Code Hook System (`hooks/tacit-capture.sh`)

A bash script that integrates with Claude Code's hook protocol. On `Stop` events, it POSTs the transcript path to `POST /api/hooks/capture`, which triggers background session mining. The hook install endpoint (`POST /api/hooks/install`) also sets `cleanupPeriodDays: 99999` in `~/.claude/settings.json` to prevent transcript deletion.

### Auto-Onboarding (`POST /api/onboarding/generate`)

Generates personalized onboarding guides for new developers. Uses Claude to organize knowledge rules into three tiers (Critical/Important/Good to Know), grouped by category, with natural-language intro paragraphs. Falls back to a template-based generator if no API key is available.

### Agent System

Agents are defined in `agents.py` using `AgentDefinition` dataclass. Each agent has:
- A prompt file in `prompts/<name>.md`
- A model assignment (sonnet or opus)
- A list of MCP tool names

Tools are defined in `tools.py` using the `@tool` decorator from `claude_agent_sdk`. The `create_tacit_tools_server()` function creates an in-process MCP server. Agents are run via `ClaudeSDKClient` with `ClaudeAgentOptions`.

Current agents (16 total):
- `pr-scanner`, `thread-analyzer`, `structural-analyzer`, `docs-analyzer`, `ci-failure-miner`, `code-analyzer` — extraction pipeline
- `anti-pattern-miner` — extracts "Do Not" rules from PR review discussions (LLM-classified, not regex-filtered)
- `domain-analyzer` — discovers domain, product, and design knowledge from README, architecture docs, ADRs, and OpenAPI specs
- `db-schema-analyzer` — extracts domain knowledge from database schemas, constraints, and sample data
- `synthesizer`, `generator` — synthesis and monolithic CLAUDE.md output
- `modular-generator` — produces `.claude/rules/` directory with path-scoped rule files
- `outcome-analyzer` — collects PR/CI metrics to measure CLAUDE.md effectiveness
- `local-extractor` — local conversation log extraction
- `pr-validator` — PR validation against rules (with provenance in review comments)
- `session-analyzer` — Claude Code transcript mining

### Database

SQLite via `aiosqlite` (WAL mode). Schema is in `database.py` as `SCHEMA` constant. Key tables: `repositories`, `knowledge_rules` (with `feedback_score`, `provenance_url`, `provenance_summary`, `applicable_paths`), `proposals`, `extraction_runs`, `decision_trail`, `mined_sessions`, `outcome_metrics`.

To reset: delete `tacit/backend/tacit.db` and restart (auto-recreates with seed data).

### Frontend

SwiftUI 3-column `NavigationSplitView`. Views connect to backend via `BackendService` (REST + WebSocket at `localhost:8000`). No external Swift dependencies. Supports: knowledge browsing with feedback, CLAUDE.md diff mode + PR creation, org-wide cross-repo pattern detection, hooks setup with live capture feed, session mining, outcome metrics dashboard, and system health monitoring.

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
- `GET /api/claude-md/{repo_id}` — Generate monolithic CLAUDE.md from knowledge base
- `GET /api/claude-md/{repo_id}/diff` — Diff existing vs generated CLAUDE.md
- `POST /api/claude-md/{repo_id}/create-pr` — Create GitHub PR with CLAUDE.md
- `GET /api/claude-rules/{repo_id}` — Generate modular `.claude/rules/` directory with path-scoped rule files

### Outcome Metrics
- `GET /api/metrics/{repo_id}` — Get historical outcome metrics (review rounds, CI failures, TTM)
- `POST /api/metrics/{repo_id}/collect` — Trigger outcome metrics collection via GitHub API

### PR Validation
- `POST /api/validate-pr` — Validate PR against knowledge rules
- `POST /api/validate-pr/post-review` — Post review comments on GitHub PR (with provenance)

### Hooks (Live Capture)
- `POST /api/hooks/capture` — Receive transcript path from Claude Code hook, trigger background mining
- `GET /api/hooks/config` — Return ready-to-use hook configuration JSON with absolute paths
- `GET /api/hooks/status` — Report hook script existence, executability, and installation status
- `POST /api/hooks/install` — Write hook script to Claude Code settings, disable transcript cleanup

### Session Mining
- `POST /api/mine-sessions` — Scan all Claude Code sessions in `~/.claude/projects/` and extract knowledge
- `GET /api/sessions` — List discovered sessions with metadata (path, message count, rules found)

### Onboarding
- `POST /api/onboarding/generate` — Generate personalized onboarding guide for a new developer

### Automation
- `POST /api/webhook/github` — GitHub webhook for incremental learning (merged PRs → auto-approve high-confidence rules, propose lower-confidence ones)

### Database Analysis
- `POST /api/analyze-db` — Analyze a database schema to extract domain knowledge (accepts `connection_string`, optional `repo_id`)

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
| `tacit/backend/pipeline.py` | Extraction orchestrator (4-phase async pipeline + session mining + incremental extraction + modular generation) |
| `tacit/backend/agents.py` | Agent definitions (model, tools, prompt mapping) — 16 agents |
| `tacit/backend/tools.py` | MCP tools (GitHub API, knowledge CRUD, PR diff, anti-patterns, outcome metrics, DB introspection) — 20 tools |
| `tacit/backend/database.py` | SQLite schema, CRUD, feedback scoring, mined sessions |
| `tacit/backend/main.py` | FastAPI app (REST + WebSocket + webhook + hooks + onboarding) |
| `tacit/backend/models.py` | Pydantic models (`KnowledgeRule`, `PRValidationResult`, etc.) |
| `tacit/backend/prompts/` | Agent prompt markdown files (16 prompts) |
| `tacit/backend/hooks/tacit-capture.sh` | Claude Code hook script for live session capture |
| `tacit/backend/templates/` | GitHub Action template for PR validation |
| `tacit/backend/samples/` | Sample webhook payload for testing |
| `tacit/backend/eval_extract.py` | Eval runner: extract → compare against ground truth |
| `tacit/backend/generated_claude_md/` | Eval outputs (generated + real CLAUDE.md pairs) |
| `tacit/TacitApp/Sources/TacitApp/Views/HooksSetupView.swift` | SwiftUI hook setup, status, and mining UI |

## Source Types and Confidence

Rules are stored with `source_type`: `pr`, `conversation`, `structure`, `docs`, `ci_fix`, `config`, `anti_pattern`.

Authority hierarchy (when rules conflict): `ci_fix`/`anti_pattern` > `structure`/`docs`/`config` > `pr` > `conversation`.

Cross-source boosting: rule found in 2+ sources gets +0.10 confidence; `ci_fix` AND `pr` → 0.95; `anti_pattern` AND `ci_fix` → 0.98.

Rules also support `provenance_url` (link to source PR/discussion), `provenance_summary` (WHY the rule exists), and `applicable_paths` (glob patterns for path-scoped delivery via `.claude/rules/`).

User feedback (`feedback_score`) tracks upvotes/downvotes per rule. Source quality stats available via `/api/stats/source-quality`.

## Webhook Setup

To enable continuous learning from merged PRs:

1. In GitHub repo settings → Webhooks → Add webhook
2. Payload URL: `https://your-tacit-host/api/webhook/github`
3. Content type: `application/json`
4. Events: Pull requests only
5. (Optional) Set `WEBHOOK_SECRET` in `.env` for HMAC verification

## Claude Code Hook Setup

To capture knowledge from live Claude Code sessions:

1. **Automatic**: Use the Tacit macOS app → Hooks sidebar → "Install Hook" button
2. **Manual**: `curl -X POST http://localhost:8000/api/hooks/install`
3. **Verify**: `curl http://localhost:8000/api/hooks/status`

The hook installs into `~/.claude/settings.json` and triggers on every Claude Code session end. It also disables the 30-day transcript cleanup to preserve session data for mining.

To mine all existing sessions before they expire: `curl -X POST http://localhost:8000/api/mine-sessions`

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

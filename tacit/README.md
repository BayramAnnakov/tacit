# Tacit

**Extract tacit team knowledge from GitHub PRs, CI failures, code configs, database schemas, and Claude Code conversations — then generate CLAUDE.md and `.claude/rules/` files.**

Tacit turns the invisible knowledge buried in code reviews and AI conversations into explicit, actionable team guidelines that Claude Code loads automatically.

## The Problem

Every team accumulates tacit knowledge — "we always validate inputs before processing", "use dependency injection for database connections", "test against non-POSIX shells". This knowledge lives scattered across PR comments, Slack threads, and individual developer memories. When new team members join or AI assistants help with code, this knowledge is lost.

## How Tacit Works

1. **Connect** a GitHub repository
2. **Extract** — 16 AI agents scan PRs, CI failures, docs, code configs, and domain docs in parallel
3. **Browse** — Review discovered rules with confidence scores, provenance links, and decision trails
4. **Propose** — Team members propose new rules from local Claude Code conversations
5. **Review** — Approve or reject proposals; approved rules join the team knowledge base
6. **Generate** — Export a monolithic CLAUDE.md or path-scoped `.claude/rules/` directory
7. **Validate** — PR validator checks new PRs against learned rules and posts review comments with provenance
8. **Learn continuously** — Webhook-driven incremental extraction from merged PRs

## Architecture

```
┌─────────────────────────────────┐
│   SwiftUI macOS App (Swift 5.9) │
│   Three-column NavigationSplit   │
│   WebSocket live streaming       │
└────────────┬────────────────────┘
             │ REST + WebSocket
┌────────────▼────────────────────┐
│   FastAPI Backend (Python 3.10)  │
│   SQLite + aiosqlite             │
│   Claude Agent SDK (16 agents)   │
│   20 MCP tools                   │
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│   Multi-Source Extraction        │
│   Phase 1: 6 parallel analyzers  │
│   Phase 2: PR thread analysis    │
│   Phase 3: Await + gather        │
│   Phase 4: Cross-source synthesis│
│   (Claude Sonnet + Opus agents)  │
└─────────────────────────────────┘
```

## CLI Tool

Extract knowledge from any GitHub repo in a single command:

```bash
cd tacit/backend && source venv/bin/activate

# Full extraction + generate CLAUDE.md
python __main__.py owner/repo

# Quick summary: stats + top anti-patterns + PR-derived rules
python __main__.py owner/repo --skip-extract --summary

# Generate modular .claude/rules/ files
python __main__.py owner/repo --modular

# Write output to a directory
python __main__.py owner/repo --modular --output ./my-project/

# Reuse existing DB (instant generation)
python __main__.py owner/repo --skip-extract
```

Example output from OpenClaw (a real open-source project with 15k+ PRs):
```
  120 rules extracted | 72 novel (60%) | 55 with provenance
  55 discovered from PRs & CI | 65 from docs & config

  Anti-Patterns (23 rules, showing top 5):
    ✗ NEVER compute a result without applying it back (PR #12669)
    ✗ NEVER reuse context window constant for output tokens (PR #12667)
    ...
```

## Quick Start

### Prerequisites
- macOS 14+ with Xcode 15+
- Python 3.10+
- Claude Code CLI (for Agent SDK)
- GitHub personal access token

### Backend Setup

```bash
cd tacit/backend
python3 -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt

# Create .env file
cat > .env << EOF
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
EOF

# Start the backend
python main.py
# → Running on http://127.0.0.1:8000
```

### Frontend Setup

```bash
cd tacit/TacitApp

# Build and run
swift build
swift run TacitApp

# Or open in Xcode:
open Package.swift
```

### Demo Mode

The backend seeds demo data on first launch:
- 8 knowledge rules from `anthropics/claude-code`
- 3 team proposals (from Alex and Sarah)
- Decision trail entries showing rule evolution
- Pre-connected repository

## Features

### Multi-Source Extraction Pipeline
6 parallel Phase 1 agents analyze repo structure, docs, CI failures, code configs, anti-patterns from PR rejections, and domain/product knowledge from README, ADRs, and architecture docs. Phase 2 deep-analyzes PR threads. Phase 4 synthesizes across all sources with cross-source confidence boosting.

### 3-Layer Generic Rule Filtering
Tacit aggressively filters generic best practices ("always write tests", "remove dead code") that add no value. Layer 1: agent prompts include a "skip generic" section with project-specificity test. Layer 2: synthesizer deduplicates and removes generic patterns. Layer 3: post-synthesis programmatic safety net catches anything the LLM missed (28 known generic patterns).

### Anti-Pattern Mining
LLM-gated extraction of "Do Not" rules from CHANGES_REQUESTED PR reviews. Captures what reviewers repeatedly reject, with diff hunks and provenance links.

### Domain Knowledge Extraction
Discovers and extracts business domain, product context, and design conventions from README, architecture docs, ADRs, OpenAPI specs, and database schemas. Goes beyond coding conventions to capture the "why" behind decisions.

### Database Schema Analysis
Connect a read-only database (PostgreSQL or SQLite) to extract domain knowledge from schema constraints, foreign key relationships, naming conventions, and sample data patterns.

### Knowledge Browser
Browse extracted rules by category (architecture, testing, style, workflow, security, performance, domain, design, product). Search with debounced queries. Upvote/downvote rules. View each rule's decision trail and provenance links.

### Modular `.claude/rules/` Generation
Generate path-scoped rule files with YAML frontmatter that Claude Code loads automatically based on which files are being edited. Rules are organized by topic (API, pipeline, testing, do-not, domain, design, product).

### Outcome Metrics
Track PR review rounds, CI failure rate, time-to-merge, and comment density to measure whether deployed rules actually improve team velocity.

### Live Extraction Stream
Watch AI agents work in real-time via WebSocket with pipeline progress bar, event cards, and rolling stats counters.

### Incremental Learning
Webhook-driven single-PR extraction from merged PRs. Auto-approves high-confidence rules (>= 0.85), creates proposals for lower-confidence ones.

### PR Validation
Validate PRs against the knowledge base. Posts review comments on GitHub with provenance links showing why each rule exists.

### Session Mining
Captures knowledge from Claude Code session transcripts via hooks. Extracts corrections, preferences, and conventions from actual AI-assisted coding sessions.

### Developer Onboarding
Generates personalized onboarding guides organized into Critical/Important/Good-to-Know tiers based on the team's knowledge base.

### Proposal Workflow
Team members propose rules from their local Claude Code conversations. Reviewers can approve (promoting to team knowledge) or reject with feedback.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check with agent/rule counts |
| GET/POST | `/api/repos` | List/create repositories |
| POST | `/api/extract/{repo_id}` | Start full extraction |
| GET | `/api/knowledge` | List rules (filter by category, repo, search) |
| GET | `/api/knowledge/{id}` | Rule detail + decision trail |
| POST | `/api/knowledge/{id}/feedback` | Upvote/downvote a rule |
| GET | `/api/knowledge/cross-repo` | Cross-repo shared patterns |
| GET/POST | `/api/proposals` | List/create proposals |
| PUT | `/api/proposals/{id}` | Approve/reject proposal |
| GET | `/api/claude-md/{repo_id}` | Generate monolithic CLAUDE.md |
| GET | `/api/claude-md/{repo_id}/diff` | Diff existing vs generated |
| POST | `/api/claude-md/{repo_id}/create-pr` | Create GitHub PR with CLAUDE.md |
| GET | `/api/claude-rules/{repo_id}` | Generate modular `.claude/rules/` |
| GET/POST | `/api/metrics/{repo_id}` | Outcome metrics (review rounds, CI, TTM) |
| POST | `/api/validate-pr` | Validate PR against rules |
| POST | `/api/validate-pr/post-review` | Post review comments on GitHub |
| POST | `/api/hooks/install` | Install Claude Code capture hook |
| POST | `/api/mine-sessions` | Mine all Claude Code sessions |
| POST | `/api/onboarding/generate` | Generate developer onboarding guide |
| POST | `/api/analyze-db` | Analyze database schema for domain knowledge |
| POST | `/api/webhook/github` | GitHub webhook for incremental learning |
| WS | `/ws` | Live extraction events |

## Tech Stack

- **Frontend**: SwiftUI, Swift 5.9, NavigationSplitView, @Observable
- **Backend**: FastAPI, aiosqlite, Pydantic, uvicorn
- **AI**: Claude Agent SDK, 16 agents (Claude Sonnet for scanning, Claude Opus for analysis/synthesis)
- **Tools**: 20 MCP tools for GitHub API, knowledge CRUD, DB introspection, PR validation
- **APIs**: GitHub REST API v3

## Eval Suite

8 evals across 8 OSS repos (langchain, deno, prisma, next.js, react, claude-code, claude-agent-sdk-python, openclaw). **Overall score: 83%.**

```bash
cd tacit/backend && source venv/bin/activate

# v1: Extraction quality vs ground truth (6 OSS repos)
python eval_extract.py

# v2: 8 capability evals (anti-patterns, provenance, path scoping, modular rules, incremental, metrics, domain knowledge, ground truth recall)
python eval_v2.py
python eval_v2.py --skip-extraction  # reuse existing DB
```

Key results:
- Anti-pattern mining: 88% (7/8 repos yield anti-patterns)
- Ground truth recall: 47% (rules independently discovered without reading CLAUDE.md)
- Provenance coverage: 98% of rules link to exact PR comments

## Built With

Built during the Anthropic Hackathon (Feb 2026) using Claude Code (Opus 4.6).

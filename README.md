![Built with Opus 4.6](https://img.shields.io/badge/Built%20with-Opus%204.6-purple)
![16 Claude Agents](https://img.shields.io/badge/Agents-16-blue)
![20 MCP Tools](https://img.shields.io/badge/MCP%20Tools-20-green)
![Eval Score 83%](https://img.shields.io/badge/Eval%20Score-83%25-brightgreen)

# Tacit

**Extract tacit team knowledge from GitHub PRs, CI failures, code configs, database schemas, and Claude Code conversations — then generate CLAUDE.md and `.claude/rules/` files.**

Tacit turns the invisible knowledge buried in code reviews and AI conversations into explicit, actionable team guidelines that Claude Code loads automatically.

<p align="center">
  <img src="tacit-demo.gif" alt="Tacit CLI demo" width="800">
</p>

## The Problem

Every team accumulates tacit knowledge — "we always validate inputs before processing", "use dependency injection for database connections", "test against non-POSIX shells". This knowledge lives scattered across PR comments, Slack threads, and individual developer memories. When new team members join or AI assistants help with code, this knowledge is lost.

## How Tacit Works

1. **Connect** a GitHub repository
2. **Extract** — 16 AI agents scan PRs, CI failures, docs, code configs, and domain docs in parallel
3. **Browse** — Review discovered rules with confidence scores, provenance links, and decision trails
4. **Generate** — Export a monolithic CLAUDE.md or path-scoped `.claude/rules/` directory
5. **Validate** — PR validator checks new PRs against learned rules and posts review comments with provenance
6. **Learn continuously** — Webhook-driven incremental extraction from merged PRs

## Architecture

```
┌────────────────────────────────┐
│   FastAPI Backend (Python 3.10) │
│   SQLite + aiosqlite            │
│   Claude Agent SDK (16 agents)  │
│   20 MCP tools                  │
└────────────┬───────────────────┘
             │
┌────────────▼───────────────────┐
│   Multi-Source Extraction       │
│   Phase 1: 6 parallel analyzers │
│   Phase 2: PR thread analysis   │
│   Phase 3: Await + gather       │
│   Phase 4: Cross-source synth.  │
│   (Claude Sonnet + Opus agents) │
└────────────────────────────────┘
```

## CLI

```bash
# Demo mode (no API keys needed):
tacit openclaw/openclaw --demo

# Full extraction on any GitHub repo:
tacit owner/repo

# Quick summary: stats + top anti-patterns + PR-derived rules
tacit owner/repo --skip-extract --summary

# Generate modular .claude/rules/ files
tacit owner/repo --modular

# Write output to a directory
tacit owner/repo --modular --output ./my-project/
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

### Try it (demo mode, no API keys)

```bash
uvx --from "git+https://github.com/BayramAnnakov/tacit.git" tacit openclaw/openclaw --demo
```

The `--demo` flag uses pre-loaded data from a real 50-PR extraction — no API keys required.

### Install and extract from your repo

```bash
pip install "git+https://github.com/BayramAnnakov/tacit.git[full]"

# Set your API keys
export ANTHROPIC_API_KEY=sk-ant-...
export GITHUB_TOKEN=ghp_...

# Extract knowledge from any GitHub repo
tacit owner/repo --summary
```

### From source (for development)

```bash
git clone https://github.com/BayramAnnakov/tacit.git && cd tacit
cd tacit/backend
python3 -m venv venv && source venv/bin/activate
pip install -r ../requirements.txt

# Create .env file
cat > .env << EOF
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
EOF

# Run CLI
python __main__.py owner/repo --summary

# Or start the API server
python main.py  # → http://127.0.0.1:8000
```

<details>
<summary>macOS Frontend (Optional)</summary>

```bash
cd tacit/TacitApp
swift build && swift run TacitApp
# Or: open Package.swift  (Xcode)
```

Requires macOS 14+ with Xcode 15+. SwiftUI three-column app connects to the backend via REST + WebSocket.
</details>

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

## Tech Stack

- **Backend**: FastAPI, aiosqlite, Pydantic, uvicorn
- **Frontend**: SwiftUI, Swift 5.9, NavigationSplitView, @Observable
- **AI**: Claude Agent SDK, 16 agents (Claude Sonnet for scanning, Claude Opus for analysis/synthesis)
- **Tools**: 20 MCP tools for GitHub API, knowledge CRUD, DB introspection, PR validation
- **APIs**: GitHub REST API v3

## Dogfooding

This repo itself uses `.claude/rules/` — the same format Tacit generates. We maintain 4 rule files (code style, workflow, testing, do-not) that guide Claude Code when working on Tacit. It's the same convention Tacit extracts from other teams' PR reviews and outputs as path-scoped rule files.

## Vision: Federated Learning for Team Knowledge

Today Tacit extracts knowledge from a repo's PR history. The next step is **federated learning for coding conventions** — where knowledge is extracted locally on each developer's machine and only the distilled rules are shared centrally.

1. **Local extraction, no raw data shared.** Each developer's Claude Code sessions stay on their machine. Tacit's hook extracts only the transferable lesson — "use X instead of Y", "always check Z before deploying" — never the conversation itself.

2. **Central aggregation with human review.** Proposed rules flow to the CLAUDE.md owner, who accepts conventions that reflect real team patterns and rejects noise. Like federated learning: local training, central model update, human-in-the-loop.

3. **The knowledge base compounds over time.** New hires get an onboarding guide generated from hundreds of real decisions. The PR validator catches violations before reviewers have to. Rules that no longer apply get downvoted and pruned.

The end state: a team's CLAUDE.md writes and maintains itself — sourced from what the team actually does, not what someone remembered to document.

## Built With

Built during the Anthropic "Built with Opus 4.6" Hackathon (Feb 2026) using Claude Code (Opus 4.6).

## License

[MIT](LICENSE)

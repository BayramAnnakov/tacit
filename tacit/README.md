# Tacit

**Extract tacit team knowledge from GitHub PRs and Claude Code conversations, surface it for review, and generate CLAUDE.md files.**

Tacit turns the invisible knowledge buried in code reviews and AI conversations into explicit, actionable team guidelines.

## The Problem

Every team accumulates tacit knowledge — "we always validate inputs before processing", "use dependency injection for database connections", "test against non-POSIX shells". This knowledge lives scattered across PR comments, Slack threads, and individual developer memories. When new team members join or AI assistants help with code, this knowledge is lost.

## How Tacit Works

1. **Connect** a GitHub repository
2. **Extract** — AI agents scan PR discussions for knowledge-rich patterns
3. **Browse** — Review discovered rules with confidence scores and decision trails
4. **Propose** — Team members propose new rules from local Claude Code conversations
5. **Review** — Approve or reject proposals; approved rules join the team knowledge base
6. **Generate** — Export a CLAUDE.md file containing your team's crystallized knowledge

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
│   Claude Agent SDK pipeline      │
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│   4-Pass Extraction Pipeline     │
│   PR Scanner → Thread Analyzer   │
│   → Synthesizer → Generator      │
│   (Claude Sonnet + Opus agents)  │
└─────────────────────────────────┘
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
pip install -r requirements.txt

# Set your GitHub token
export GITHUB_TOKEN=ghp_your_token_here

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

### Live Extraction Stream
Watch AI agents analyze PR discussions in real-time with a pipeline progress bar, event cards, and rolling stats counters.

### Knowledge Browser
Browse extracted rules by category (architecture, testing, style, workflow, security, performance). Search with debounced queries. View each rule's decision trail showing how it was discovered and evolved.

### Proposal Workflow
Team members propose rules from their local Claude Code conversations. Reviewers can approve (promoting to team knowledge) or reject with feedback.

### CLAUDE.md Generator
Generate a structured CLAUDE.md file from your team's knowledge base. Live preview with markdown rendering, copy to clipboard, or export as file.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET/POST | `/api/repos` | List/create repositories |
| POST | `/api/extract/{repo_id}` | Start extraction |
| GET | `/api/knowledge` | List rules (filter by category, search) |
| GET | `/api/knowledge/{id}` | Rule detail + decision trail |
| GET/POST | `/api/proposals` | List/create proposals |
| PUT | `/api/proposals/{id}` | Approve/reject proposal |
| GET | `/api/claude-md/{repo_id}` | Generate CLAUDE.md |
| WS | `/ws` | Live extraction events |

## Tech Stack

- **Frontend**: SwiftUI, Swift 5.9, NavigationSplitView, @Observable
- **Backend**: FastAPI, aiosqlite, Pydantic, uvicorn
- **AI**: Claude Agent SDK, Claude Sonnet (scanning), Claude Opus (analysis)
- **APIs**: GitHub REST API v3

## Built With

Built during the Anthropic Hackathon (Feb 2026) using Claude Code (Opus 4.6).

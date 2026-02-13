---
description: MCP tools -- GitHub API, knowledge CRUD, local logs
paths:
  - "tacit/backend/tools.py"
---

- 14 MCP tools registered in `create_tacit_tools_server()`
- Use `@tool(name=..., description=..., input_schema={...})` decorator from `claude_agent_sdk`
- Tool names listed in `_RAW_TOOL_NAMES`, prefixed with `mcp__tacit_tools__` for `allowed_tools`
- `store_knowledge` accepts `provenance_url`, `provenance_summary`, `applicable_paths`
- All tool functions are async and accept `args: dict`

### GitHub tools
- `github_fetch_prs` -- PR metadata with review states and first-timer detection
- `github_fetch_comments` -- issue comments + inline review comments + reviews
- `github_fetch_repo_structure` -- file tree, commits, branch rulesets
- `github_fetch_docs` -- CONTRIBUTING.md, README, CLAUDE.md/AGENTS.md
- `github_fetch_ci_fixes` -- CI failure-to-fix diffs
- `github_fetch_code_samples` -- config files (test, linter, CI, package)
- `github_fetch_pr_diff` -- changed files with patches
- `github_fetch_rejected_patterns` -- CHANGES_REQUESTED review comments
- `github_fetch_outcome_metrics` -- PR/CI metrics over time period

### Knowledge tools
- `store_knowledge`, `search_knowledge`, `list_all_knowledge`, `delete_knowledge`

### Local tools
- `read_claude_logs` -- reads JSONL transcripts from `~/.claude/projects/`

---
description: MCP tools -- GitHub API, knowledge CRUD, local logs
paths:
  - "tacit/backend/tools.py"
---

- 20 MCP tools registered in `create_tacit_tools_server()` (16 in tools.py + 4 from db_tools.py)
- Use `@tool(name=..., description=..., input_schema={...})` decorator from `claude_agent_sdk`
- Tool names listed in `_RAW_TOOL_NAMES`, prefixed with `mcp__tacit_tools__` for `allowed_tools`
- `store_knowledge` accepts `provenance_url`, `provenance_summary`, `applicable_paths`
- All tool functions are async and accept `args: dict`

### GitHub tools
- `github_fetch_prs` -- PR metadata with review states and first-timer detection
- `github_fetch_comments` -- issue comments + inline review comments + reviews
- `github_fetch_repo_structure` -- file tree, commits, branch rulesets
- `github_fetch_docs` -- CONTRIBUTING.md, README, CLAUDE.md/AGENTS.md
- `github_fetch_file_content` -- fetch specific file by path (for domain docs, ADRs, specs)
- `github_fetch_readme_full` -- complete README without section filtering
- `github_fetch_ci_fixes` -- CI failure-to-fix diffs
- `github_fetch_code_samples` -- config files (test, linter, CI, package)
- `github_fetch_pr_diff` -- changed files with patches
- `github_fetch_rejected_patterns` -- CHANGES_REQUESTED review comments
- `github_fetch_outcome_metrics` -- PR/CI metrics over time period

### Knowledge tools
- `store_knowledge`, `search_knowledge`, `list_all_knowledge`, `delete_knowledge`

### Database introspection tools (db_tools.py)
- `db_connect` -- connect read-only to PostgreSQL or SQLite
- `db_inspect_schema` -- list tables, columns, constraints, indexes
- `db_sample_data` -- fetch sample rows from a table
- `db_query_readonly` -- execute read-only SQL queries

### Local tools
- `read_claude_logs` -- reads JSONL transcripts from `~/.claude/projects/`

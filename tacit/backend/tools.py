"""MCP tools for the extraction pipeline using Claude Agent SDK @tool decorator."""

import json
import glob as globlib
from pathlib import Path

import httpx

from claude_agent_sdk import tool, create_sdk_mcp_server
import database as db


# --------------- GitHub Tools ---------------

@tool(
    name="github_fetch_prs",
    description="Fetch pull requests from a GitHub repository. Returns PR metadata including title, number, author, labels, and comment counts.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "state": {"type": "string", "description": "PR state: open, closed, or all", "default": "closed"},
            "per_page": {"type": "integer", "description": "Number of PRs to fetch (max 100)", "default": 30},
            "github_token": {"type": "string", "description": "GitHub API token"},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_prs(args: dict) -> dict:
    repo = args["repo"]
    state = args.get("state", "closed")
    per_page = min(args.get("per_page", 30), 100)
    token = args["github_token"]

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls",
            params={"state": state, "per_page": per_page, "sort": "updated", "direction": "desc"},
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return {
                "content": [{"type": "text", "text": f"GitHub API error {resp.status_code}: {resp.text}"}],
                "is_error": True,
            }

        prs = resp.json()
        summary = []
        for pr in prs:
            summary.append({
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "state": pr["state"],
                "comments": pr.get("comments", 0) + pr.get("review_comments", 0),
                "labels": [l["name"] for l in pr.get("labels", [])],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "merged": pr.get("merged_at") is not None,
            })

    return {"content": [{"type": "text", "text": json.dumps(summary, indent=2)}]}


@tool(
    name="github_fetch_comments",
    description="Fetch all comments and review comments for a specific pull request. Includes both issue-style comments and inline code review comments.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "pr_number": {"type": "integer", "description": "Pull request number"},
            "github_token": {"type": "string", "description": "GitHub API token"},
        },
        "required": ["repo", "pr_number", "github_token"],
    },
)
async def github_fetch_comments(args: dict) -> dict:
    repo = args["repo"]
    pr_number = args["pr_number"]
    token = args["github_token"]

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    all_comments = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Fetch issue comments
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            for c in resp.json():
                all_comments.append({
                    "type": "issue_comment",
                    "author": c["user"]["login"],
                    "body": c["body"],
                    "created_at": c["created_at"],
                })

        # Fetch review comments (inline code review)
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments",
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            for c in resp.json():
                all_comments.append({
                    "type": "review_comment",
                    "author": c["user"]["login"],
                    "body": c["body"],
                    "path": c.get("path", ""),
                    "diff_hunk": c.get("diff_hunk", ""),
                    "created_at": c["created_at"],
                })

        # Fetch reviews themselves
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            for r in resp.json():
                if r.get("body"):
                    all_comments.append({
                        "type": "review",
                        "author": r["user"]["login"],
                        "body": r["body"],
                        "state": r["state"],
                        "created_at": r["submitted_at"],
                    })

    # Sort by creation time
    all_comments.sort(key=lambda c: c.get("created_at", ""))

    return {"content": [{"type": "text", "text": json.dumps(all_comments, indent=2)}]}


# --------------- Local Log Tools ---------------

@tool(
    name="read_claude_logs",
    description="Read Claude Code JSONL conversation logs from a project directory. Returns recent conversations with assistant messages and tool usage.",
    input_schema={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the project. Logs are read from ~/.claude/projects/"},
            "limit": {"type": "integer", "description": "Max number of log entries to return", "default": 50},
        },
        "required": ["project_path"],
    },
)
async def read_claude_logs(args: dict) -> dict:
    project_path = args["project_path"]
    limit = args.get("limit", 50)

    # Claude Code stores logs in ~/.claude/projects/<encoded-path>/
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return {"content": [{"type": "text", "text": "No Claude Code projects directory found."}]}

    # Find matching project directories (path is encoded with dashes)
    encoded = project_path.replace("/", "-").lstrip("-")
    matches = list(claude_dir.glob(f"*{encoded}*"))

    if not matches:
        # Try listing all and doing partial match
        all_dirs = [d for d in claude_dir.iterdir() if d.is_dir()]
        return {
            "content": [{"type": "text", "text": f"No project logs found for '{project_path}'. "
                         f"Available: {[d.name for d in all_dirs[:10]]}"}],
        }

    entries = []
    for proj_dir in matches:
        # Look for JSONL conversation files
        for jsonl_file in sorted(proj_dir.glob("*.jsonl"), reverse=True):
            with open(jsonl_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Only include assistant messages and tool results
                        if entry.get("role") in ("assistant", "tool"):
                            entries.append({
                                "role": entry.get("role"),
                                "content": entry.get("content", "")[:500],  # Truncate
                                "timestamp": entry.get("timestamp", ""),
                            })
                    except json.JSONDecodeError:
                        continue
                    if len(entries) >= limit:
                        break
            if len(entries) >= limit:
                break

    return {"content": [{"type": "text", "text": json.dumps(entries, indent=2)}]}


# --------------- Knowledge Storage Tools ---------------

@tool(
    name="store_knowledge",
    description="Store an extracted knowledge rule in the database. Returns the created rule with its ID.",
    input_schema={
        "type": "object",
        "properties": {
            "rule_text": {"type": "string", "description": "The knowledge rule text"},
            "category": {"type": "string", "description": "Category: architecture, testing, style, workflow, security, performance, general"},
            "confidence": {"type": "number", "description": "Confidence score 0.0-1.0"},
            "source_type": {"type": "string", "description": "Source type: 'pr' or 'conversation'"},
            "source_ref": {"type": "string", "description": "Reference to the source (PR URL or log path)"},
            "repo_id": {"type": "integer", "description": "Repository ID (optional)"},
        },
        "required": ["rule_text", "category", "confidence", "source_type", "source_ref"],
    },
)
async def store_knowledge(args: dict) -> dict:
    rule = await db.insert_rule(
        rule_text=args["rule_text"],
        category=args["category"],
        confidence=args["confidence"],
        source_type=args["source_type"],
        source_ref=args["source_ref"],
        repo_id=args.get("repo_id"),
    )

    # Add decision trail entry
    if rule.get("id"):
        await db.add_trail_entry(
            rule_id=rule["id"],
            event_type="created",
            description=f"Extracted from {args['source_type']} source",
            source_ref=args["source_ref"],
        )

    return {"content": [{"type": "text", "text": json.dumps(rule, default=str)}]}


@tool(
    name="search_knowledge",
    description="Search existing knowledge rules by text query and optional category/repo filters. Returns matching rules ranked by confidence.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text to search for in rule text"},
            "category": {"type": "string", "description": "Filter by category (optional)"},
            "repo_id": {"type": "integer", "description": "Filter by repository ID (optional)"},
        },
        "required": ["query"],
    },
)
async def search_knowledge(args: dict) -> dict:
    results = await db.search_rules(
        query_text=args["query"],
        category=args.get("category"),
        repo_id=args.get("repo_id"),
    )
    return {"content": [{"type": "text", "text": json.dumps(results, default=str)}]}


# --------------- Create the MCP Server ---------------

SERVER_NAME = "tacit_tools"


def create_tacit_tools_server():
    """Create an in-process MCP server with all Tacit extraction tools."""
    return create_sdk_mcp_server(
        name=SERVER_NAME,
        version="1.0.0",
        tools=[
            github_fetch_prs,
            github_fetch_comments,
            read_claude_logs,
            store_knowledge,
            search_knowledge,
        ],
    )


# Raw tool names (without MCP prefix)
_RAW_TOOL_NAMES = [
    "github_fetch_prs",
    "github_fetch_comments",
    "read_claude_logs",
    "store_knowledge",
    "search_knowledge",
]

# MCP-prefixed tool names for allowed_tools
TOOL_NAMES = [f"mcp__{SERVER_NAME}__{name}" for name in _RAW_TOOL_NAMES]

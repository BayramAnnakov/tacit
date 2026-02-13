"""MCP tools for the extraction pipeline using Claude Agent SDK @tool decorator."""

import json
import re
from collections import Counter
from pathlib import Path

import httpx

from claude_agent_sdk import tool, create_sdk_mcp_server
import database as db


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


# --------------- GitHub Tools ---------------

@tool(
    name="github_fetch_prs",
    description="Fetch pull requests from a GitHub repository. Returns PR metadata including title, number, author, labels, comment counts, review states, and first-timer flags.",
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
    headers = _gh_headers(token)

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

        # Count author PR frequency to detect first-timers
        author_counts: Counter = Counter()
        for pr in prs:
            author_counts[pr["user"]["login"]] += 1

        # Fetch review states for each PR (batch — only for PRs with comments)
        review_states: dict[int, list[str]] = {}
        for pr in prs:
            pr_num = pr["number"]
            if pr.get("review_comments", 0) > 0 or pr.get("comments", 0) > 0:
                rev_resp = await client.get(
                    f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews",
                    headers=headers,
                    params={"per_page": 10},
                    timeout=15,
                )
                if rev_resp.status_code == 200:
                    review_states[pr_num] = [r["state"] for r in rev_resp.json()]

        summary = []
        for pr in prs:
            author = pr["user"]["login"]
            pr_num = pr["number"]
            states = review_states.get(pr_num, [])
            summary.append({
                "number": pr_num,
                "title": pr["title"],
                "author": author,
                "state": pr["state"],
                "comments": pr.get("comments", 0) + pr.get("review_comments", 0),
                "labels": [l["name"] for l in pr.get("labels", [])],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "merged": pr.get("merged_at") is not None,
                "has_changes_requested": "CHANGES_REQUESTED" in states,
                "review_states": states,
                "is_first_timer": author_counts[author] <= 2,
                "changed_files": pr.get("changed_files", 0),
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


# --------------- Structural Analysis Tools ---------------

@tool(
    name="github_fetch_repo_structure",
    description="Fetch repo tree, recent commits, and branch rulesets in ~6 API calls. Returns file paths (naming conventions, test layout, tooling), commit message patterns, and enforced branch policies.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "github_token": {"type": "string", "description": "GitHub API token"},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_repo_structure(args: dict) -> dict:
    repo = args["repo"]
    token = args["github_token"]
    headers = _gh_headers(token)
    result: dict = {"tree": [], "commits": [], "rulesets": [], "errors": []}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. Get default branch SHA
        repo_resp = await client.get(
            f"https://api.github.com/repos/{repo}",
            headers=headers, timeout=15,
        )
        if repo_resp.status_code != 200:
            return {"content": [{"type": "text", "text": f"GitHub API error {repo_resp.status_code}: {repo_resp.text}"}], "is_error": True}
        default_branch = repo_resp.json().get("default_branch", "main")

        # 2. Fetch recursive tree
        tree_resp = await client.get(
            f"https://api.github.com/repos/{repo}/git/trees/{default_branch}",
            params={"recursive": "1"},
            headers=headers, timeout=30,
        )
        if tree_resp.status_code == 200:
            tree_data = tree_resp.json()
            # Return only paths (skip blob content), limit to 2000 entries
            paths = [item["path"] for item in tree_data.get("tree", []) if item["type"] in ("blob", "tree")]
            result["tree"] = paths[:2000]
            result["tree_truncated"] = tree_data.get("truncated", False)
        else:
            result["errors"].append(f"Tree fetch failed: {tree_resp.status_code}")

        # 3. Fetch recent commits (30)
        commits_resp = await client.get(
            f"https://api.github.com/repos/{repo}/commits",
            params={"per_page": 30, "sha": default_branch},
            headers=headers, timeout=15,
        )
        if commits_resp.status_code == 200:
            for c in commits_resp.json():
                msg = c["commit"]["message"]
                result["commits"].append({
                    "sha": c["sha"][:8],
                    "message": msg[:200],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                    "is_merge": msg.startswith("Merge "),
                })
        else:
            result["errors"].append(f"Commits fetch failed: {commits_resp.status_code}")

        # 4. Fetch branch rulesets (may require admin, gracefully degrade)
        rulesets_resp = await client.get(
            f"https://api.github.com/repos/{repo}/rulesets",
            headers=headers, timeout=15,
        )
        if rulesets_resp.status_code == 200:
            for rs in rulesets_resp.json():
                result["rulesets"].append({
                    "name": rs.get("name"),
                    "enforcement": rs.get("enforcement"),
                    "target": rs.get("target"),
                    "rules": [r.get("type") for r in rs.get("rules", [])],
                })
        # Fallback: try branch protection (older API)
        elif rulesets_resp.status_code in (404, 403):
            bp_resp = await client.get(
                f"https://api.github.com/repos/{repo}/branches/{default_branch}/protection",
                headers=headers, timeout=15,
            )
            if bp_resp.status_code == 200:
                bp = bp_resp.json()
                protection = {}
                if bp.get("required_status_checks"):
                    protection["required_checks"] = bp["required_status_checks"].get("contexts", [])
                    protection["strict"] = bp["required_status_checks"].get("strict", False)
                if bp.get("required_pull_request_reviews"):
                    protection["required_approvals"] = bp["required_pull_request_reviews"].get("required_approving_review_count", 0)
                    protection["code_owners_required"] = bp["required_pull_request_reviews"].get("require_code_owner_reviews", False)
                if bp.get("required_linear_history"):
                    protection["linear_history"] = bp["required_linear_history"].get("enabled", False)
                if protection:
                    result["rulesets"].append({"type": "branch_protection", **protection})

    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


@tool(
    name="github_fetch_docs",
    description="Fetch CONTRIBUTING.md, README.md (setup sections only), and any existing CLAUDE.md/AGENTS.md from a repo. Pre-filters README to development-relevant sections.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "github_token": {"type": "string", "description": "GitHub API token"},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_docs(args: dict) -> dict:
    repo = args["repo"]
    token = args["github_token"]
    headers = _gh_headers(token)
    headers["Accept"] = "application/vnd.github.v3.raw"

    doc_files = [
        "CONTRIBUTING.md",
        "contributing.md",
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        "AGENTS.md",
        "README.md",
        "docs/CONTRIBUTING.md",
        "docs/contributing.md",
        ".github/CONTRIBUTING.md",
    ]

    result: dict = {}
    setup_keywords = re.compile(
        r"(setup|install|develop|getting.started|contributing|prerequisit|build|quick.start|usage|requirements)",
        re.IGNORECASE,
    )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for filepath in doc_files:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{filepath}",
                headers=headers, timeout=15,
            )
            if resp.status_code != 200:
                continue

            content = resp.text
            name = filepath.split("/")[-1].upper()

            # For README.md, extract only dev-relevant sections
            if name == "README.MD":
                sections = _extract_relevant_sections(content, setup_keywords)
                if sections:
                    result[filepath] = sections
            else:
                # Full content for CONTRIBUTING, CLAUDE, AGENTS
                result[filepath] = content[:15000]  # Cap at 15k chars

    if not result:
        return {"content": [{"type": "text", "text": "No contributing/setup documentation found in this repository."}]}

    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def _extract_relevant_sections(markdown: str, pattern: re.Pattern) -> str:
    """Extract markdown sections whose headings match the pattern."""
    lines = markdown.split("\n")
    sections: list[str] = []
    capturing = False
    current_level = 0

    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2)
            if pattern.search(title):
                capturing = True
                current_level = level
                sections.append(line)
            elif capturing and level <= current_level:
                capturing = False
            elif capturing:
                sections.append(line)
        elif capturing:
            sections.append(line)

    return "\n".join(sections)[:10000]


@tool(
    name="github_fetch_ci_fixes",
    description="Mine CI failure→fix patterns from recent PRs. Finds PRs where CI checks failed then passed, and returns the fix commit diffs that reveal implicit conventions.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "github_token": {"type": "string", "description": "GitHub API token"},
            "max_prs": {"type": "integer", "description": "Max PRs to scan (default 30)", "default": 30},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_ci_fixes(args: dict) -> dict:
    repo = args["repo"]
    token = args["github_token"]
    max_prs = min(args.get("max_prs", 30), 50)
    headers = _gh_headers(token)

    ci_fixes: list[dict] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Fetch recent merged PRs
        pr_resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls",
            params={"state": "closed", "per_page": max_prs, "sort": "updated", "direction": "desc"},
            headers=headers, timeout=30,
        )
        if pr_resp.status_code != 200:
            return {"content": [{"type": "text", "text": f"GitHub API error {pr_resp.status_code}: {pr_resp.text}"}], "is_error": True}

        prs = [p for p in pr_resp.json() if p.get("merged_at")]

        for pr in prs[:max_prs]:
            pr_num = pr["number"]

            # Fetch commits for this PR
            commits_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/commits",
                headers=headers, timeout=15,
            )
            if commits_resp.status_code != 200:
                continue
            commits = commits_resp.json()
            if len(commits) < 2:
                continue  # Need at least 2 commits to see a fix pattern

            # Check for CI failures on earlier commits
            found_failure = False
            failed_check_name = ""
            fix_commit_sha = ""

            for i, commit in enumerate(commits):
                sha = commit["sha"]
                checks_resp = await client.get(
                    f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs",
                    headers=headers,
                    params={"per_page": 20},
                    timeout=15,
                )
                if checks_resp.status_code != 200:
                    continue

                runs = checks_resp.json().get("check_runs", [])
                failed_checks = [r for r in runs if r.get("conclusion") == "failure"]

                if failed_checks and not found_failure:
                    found_failure = True
                    failed_check_name = failed_checks[0].get("name", "unknown")
                elif found_failure and i > 0:
                    # This commit came after a failure — check if it passed
                    passed = [r for r in runs if r.get("conclusion") == "success" and r.get("name") == failed_check_name]
                    if passed:
                        fix_commit_sha = sha
                        break

            if not fix_commit_sha:
                continue

            # Fetch the fix commit diff
            diff_resp = await client.get(
                f"https://api.github.com/repos/{repo}/commits/{fix_commit_sha}",
                headers=headers, timeout=15,
            )
            if diff_resp.status_code != 200:
                continue

            commit_data = diff_resp.json()
            files_changed = []
            for f in commit_data.get("files", [])[:10]:
                files_changed.append({
                    "filename": f["filename"],
                    "status": f["status"],
                    "patch": (f.get("patch") or "")[:500],
                })

            ci_fixes.append({
                "pr_number": pr_num,
                "pr_title": pr["title"],
                "failed_check": failed_check_name,
                "fix_commit_sha": fix_commit_sha[:8],
                "fix_commit_message": commit_data["commit"]["message"][:200],
                "files_changed": files_changed,
                "author": pr["user"]["login"],
            })

            # Limit to 10 CI fix patterns to avoid excessive API calls
            if len(ci_fixes) >= 10:
                break

    if not ci_fixes:
        return {"content": [{"type": "text", "text": "No CI failure→fix patterns found in recent PRs."}]}

    return {"content": [{"type": "text", "text": json.dumps(ci_fixes, indent=2)}]}


@tool(
    name="github_fetch_code_samples",
    description="Fetch key configuration and code files from a repository: test configs, linter configs, CI workflows, and package manager configs. Returns file contents for convention extraction.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "github_token": {"type": "string", "description": "GitHub API token"},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_code_samples(args: dict) -> dict:
    repo = args["repo"]
    token = args["github_token"]
    headers = _gh_headers(token)
    headers["Accept"] = "application/vnd.github.v3.raw"

    config_paths = [
        # Test configs
        "jest.config.js", "jest.config.ts", "jest.config.mjs",
        "pytest.ini", "setup.cfg", "pyproject.toml",
        "vitest.config.ts", "vitest.config.js",
        # Linter configs
        ".eslintrc.json", ".eslintrc.js", ".eslintrc.yml",
        ".ruff.toml", "ruff.toml",
        "biome.json", "biome.jsonc",
        ".prettierrc", ".prettierrc.json",
        # CI workflows
        ".github/workflows/ci.yml", ".github/workflows/ci.yaml",
        ".github/workflows/test.yml", ".github/workflows/tests.yml",
        ".github/workflows/lint.yml", ".github/workflows/build.yml",
        # Package configs
        "package.json", "Makefile", "Cargo.toml",
        "tsconfig.json", "Dockerfile",
    ]

    result: dict[str, str] = {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for filepath in config_paths:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{filepath}",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                content = resp.text[:10000]
                result[filepath] = content

    if not result:
        return {"content": [{"type": "text", "text": "No configuration files found in this repository."}]}

    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


@tool(
    name="github_fetch_pr_diff",
    description="Fetch the file changes (diff) for a specific pull request. Returns changed files with their patches.",
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
async def github_fetch_pr_diff(args: dict) -> dict:
    repo = args["repo"]
    pr_number = args["pr_number"]
    token = args["github_token"]
    headers = _gh_headers(token)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files",
            headers=headers, timeout=30,
            params={"per_page": 100},
        )
        if resp.status_code != 200:
            return {"content": [{"type": "text", "text": f"GitHub API error {resp.status_code}: {resp.text}"}], "is_error": True}

        files = []
        for f in resp.json():
            files.append({
                "filename": f["filename"],
                "status": f["status"],
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": (f.get("patch") or "")[:2000],
            })

    return {"content": [{"type": "text", "text": json.dumps(files, indent=2)}]}


# --------------- Anti-Pattern Mining Tools ---------------

# Minimum review comments for a PR to be worth sending to Claude for analysis.
# PRs with fewer comments rarely contain meaningful correction patterns.
_MIN_REVIEW_COMMENTS = 3


@tool(
    name="github_fetch_rejected_patterns",
    description="Fetch PRs with substantive review discussions for anti-pattern analysis. Selects PRs with CHANGES_REQUESTED reviews OR those with 3+ inline review comments (indicating code-level feedback). Returns all review comments, diff hunks, and review bodies so the anti-pattern-miner agent can use LLM judgment to identify rejection/correction patterns.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "github_token": {"type": "string", "description": "GitHub API token"},
            "max_prs": {"type": "integer", "description": "Max PRs to scan (default 30)", "default": 30},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_rejected_patterns(args: dict) -> dict:
    repo = args["repo"]
    token = args["github_token"]
    max_prs = min(args.get("max_prs", 30), 50)
    headers = _gh_headers(token)

    patterns: list[dict] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Fetch recent closed PRs (merged ones have review trails too)
        pr_resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls",
            params={"state": "closed", "per_page": max_prs, "sort": "updated", "direction": "desc"},
            headers=headers, timeout=30,
        )
        if pr_resp.status_code != 200:
            return {"content": [{"type": "text", "text": f"GitHub API error {pr_resp.status_code}: {pr_resp.text}"}], "is_error": True}

        prs = pr_resp.json()

        for pr in prs:
            pr_num = pr["number"]

            # Fetch reviews for this PR
            rev_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews",
                headers=headers, params={"per_page": 20}, timeout=15,
            )
            if rev_resp.status_code != 200:
                continue

            reviews = rev_resp.json()
            changes_requested = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]
            has_formal_rejection = len(changes_requested) > 0

            # Fetch inline review comments (code-level feedback)
            comments_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/comments",
                headers=headers, params={"per_page": 50}, timeout=15,
            )
            if comments_resp.status_code != 200:
                continue

            raw_comments = comments_resp.json()

            # Selection gate: include PR if it has formal CHANGES_REQUESTED
            # OR enough inline review comments to indicate substantive discussion.
            # No regex filtering — let the Claude agent decide what's a rejection.
            if not has_formal_rejection and len(raw_comments) < _MIN_REVIEW_COMMENTS:
                continue

            # Pass ALL review comments to the agent for LLM-based classification
            review_comments = []
            for c in raw_comments:
                body = c.get("body", "")
                review_comments.append({
                    "author": c["user"]["login"],
                    "body": body[:500],
                    "path": c.get("path", ""),
                    "diff_hunk": (c.get("diff_hunk") or "")[:400],
                    "has_suggestion_block": "```suggestion" in body,
                })

            # Collect all review-level bodies (top-level review summaries)
            review_bodies = []
            for r in reviews:
                body = (r.get("body") or "").strip()
                if body:
                    review_bodies.append({
                        "author": r["user"]["login"],
                        "state": r.get("state", ""),
                        "body": body[:500],
                    })

            patterns.append({
                "pr_number": pr_num,
                "pr_title": pr["title"],
                "pr_url": pr.get("html_url", f"https://github.com/{repo}/pull/{pr_num}"),
                "author": pr["user"]["login"],
                "merged": pr.get("merged_at") is not None,
                "has_formal_rejection": has_formal_rejection,
                "review_bodies": review_bodies,
                "inline_review_comments": review_comments[:20],
                "total_review_comments": len(raw_comments),
                "review_rounds": len(reviews),
            })

            if len(patterns) >= 10:
                break

    if not patterns:
        return {"content": [{"type": "text", "text": "No rejection patterns found in recent PRs."}]}

    return {"content": [{"type": "text", "text": json.dumps(patterns, indent=2)}]}


# --------------- Outcome Metrics Tools ---------------

@tool(
    name="github_fetch_outcome_metrics",
    description="Fetch PR and CI metrics for a repository over a given time period. Returns average review rounds, CI failure rate, comment density, and time-to-merge.",
    input_schema={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Full repo name e.g. 'owner/repo'"},
            "github_token": {"type": "string", "description": "GitHub API token"},
            "days": {"type": "integer", "description": "Number of days to look back (default 14)", "default": 14},
        },
        "required": ["repo", "github_token"],
    },
)
async def github_fetch_outcome_metrics(args: dict) -> dict:
    repo = args["repo"]
    token = args["github_token"]
    days = min(args.get("days", 14), 90)
    headers = _gh_headers(token)

    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    metrics = {
        "period_days": days,
        "total_prs": 0,
        "avg_review_rounds": 0.0,
        "ci_failure_rate": 0.0,
        "avg_comments_per_pr": 0.0,
        "avg_time_to_merge_hours": 0.0,
        "first_timer_avg_ttm_hours": 0.0,
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Fetch merged PRs in the period
        pr_resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls",
            params={"state": "closed", "per_page": 50, "sort": "updated", "direction": "desc"},
            headers=headers, timeout=30,
        )
        if pr_resp.status_code != 200:
            return {"content": [{"type": "text", "text": f"GitHub API error {pr_resp.status_code}"}], "is_error": True}

        prs = [p for p in pr_resp.json() if p.get("merged_at") and p.get("created_at", "") >= since]
        metrics["total_prs"] = len(prs)

        if not prs:
            return {"content": [{"type": "text", "text": json.dumps(metrics, indent=2)}]}

        # Count author frequency for first-timer detection
        author_counts: Counter = Counter()
        for p in pr_resp.json():
            author_counts[p["user"]["login"]] += 1

        total_comments = 0
        total_review_rounds = 0
        total_ttm = 0.0
        first_timer_ttms: list[float] = []
        ci_failures = 0
        ci_total = 0

        for pr in prs[:30]:  # Limit API calls
            pr_num = pr["number"]
            total_comments += pr.get("comments", 0) + pr.get("review_comments", 0)

            # Count review rounds
            rev_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews",
                headers=headers, params={"per_page": 10}, timeout=15,
            )
            if rev_resp.status_code == 200:
                total_review_rounds += len(rev_resp.json())

            # Time to merge
            created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
            merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            ttm_hours = (merged - created).total_seconds() / 3600
            total_ttm += ttm_hours

            if author_counts[pr["user"]["login"]] <= 2:
                first_timer_ttms.append(ttm_hours)

            # Check CI status on head commit
            commits_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/commits",
                headers=headers, params={"per_page": 1}, timeout=10,
            )
            if commits_resp.status_code == 200:
                commits = commits_resp.json()
                if commits:
                    sha = commits[-1]["sha"]
                    checks_resp = await client.get(
                        f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs",
                        headers=headers, params={"per_page": 5}, timeout=10,
                    )
                    if checks_resp.status_code == 200:
                        runs = checks_resp.json().get("check_runs", [])
                        ci_total += len(runs)
                        ci_failures += sum(1 for r in runs if r.get("conclusion") == "failure")

        n = len(prs[:30])
        metrics["avg_review_rounds"] = round(total_review_rounds / n, 2) if n else 0
        metrics["avg_comments_per_pr"] = round(total_comments / n, 2) if n else 0
        metrics["avg_time_to_merge_hours"] = round(total_ttm / n, 1) if n else 0
        metrics["ci_failure_rate"] = round(ci_failures / ci_total, 3) if ci_total else 0
        metrics["first_timer_avg_ttm_hours"] = round(
            sum(first_timer_ttms) / len(first_timer_ttms), 1
        ) if first_timer_ttms else 0

    return {"content": [{"type": "text", "text": json.dumps(metrics, indent=2)}]}


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
    description="Store an extracted knowledge rule in the database. Returns the created rule with its ID. Supports provenance tracking and path-scoped rules.",
    input_schema={
        "type": "object",
        "properties": {
            "rule_text": {"type": "string", "description": "The knowledge rule text"},
            "category": {"type": "string", "description": "Category: architecture, testing, style, workflow, security, performance, general"},
            "confidence": {"type": "number", "description": "Confidence score 0.0-1.0"},
            "source_type": {"type": "string", "description": "Source type: 'pr', 'conversation', 'structure', 'docs', 'ci_fix', 'config', 'anti_pattern'"},
            "source_ref": {"type": "string", "description": "Reference to the source (PR URL or log path)"},
            "repo_id": {"type": "integer", "description": "Repository ID (optional)"},
            "provenance_url": {"type": "string", "description": "URL to the source PR/discussion/CI run (optional)"},
            "provenance_summary": {"type": "string", "description": "Brief explanation of WHY this rule exists — what happened that led to it (optional)"},
            "applicable_paths": {"type": "string", "description": "Comma-separated glob patterns for files this rule applies to, e.g. 'src/api/**/*.ts,src/db/**'. Empty means applies everywhere. (optional)"},
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
        provenance_url=args.get("provenance_url", ""),
        provenance_summary=args.get("provenance_summary", ""),
        applicable_paths=args.get("applicable_paths", ""),
    )

    # Add decision trail entry
    if rule.get("id"):
        desc = f"Extracted from {args['source_type']} source"
        if args.get("provenance_summary"):
            desc += f" — {args['provenance_summary'][:200]}"
        await db.add_trail_entry(
            rule_id=rule["id"],
            event_type="created",
            description=desc,
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


@tool(
    name="list_all_knowledge",
    description="List ALL knowledge rules for a repository. Use this to get a complete view of all rules for deduplication and synthesis. Returns rules sorted by confidence (highest first).",
    input_schema={
        "type": "object",
        "properties": {
            "repo_id": {"type": "integer", "description": "Repository ID to list rules for"},
            "category": {"type": "string", "description": "Filter by category (optional)"},
        },
        "required": [],
    },
)
async def list_all_knowledge(args: dict) -> dict:
    results = await db.list_rules(
        category=args.get("category"),
        repo_id=args.get("repo_id"),
    )
    return {"content": [{"type": "text", "text": json.dumps(results, default=str)}]}


@tool(
    name="delete_knowledge",
    description="Delete a knowledge rule by its ID. Use this during synthesis to remove duplicate or low-quality rules after merging them into a better version.",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "ID of the rule to delete"},
        },
        "required": ["rule_id"],
    },
)
async def delete_knowledge(args: dict) -> dict:
    rule_id = args["rule_id"]
    success = await db.delete_rule(rule_id)
    if success:
        return {"content": [{"type": "text", "text": f"Rule {rule_id} deleted successfully."}]}
    return {"content": [{"type": "text", "text": f"Rule {rule_id} not found."}], "is_error": True}


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
            github_fetch_repo_structure,
            github_fetch_docs,
            github_fetch_ci_fixes,
            github_fetch_code_samples,
            github_fetch_pr_diff,
            github_fetch_rejected_patterns,
            github_fetch_outcome_metrics,
            read_claude_logs,
            store_knowledge,
            search_knowledge,
            list_all_knowledge,
            delete_knowledge,
        ],
    )


# Raw tool names (without MCP prefix)
_RAW_TOOL_NAMES = [
    "github_fetch_prs",
    "github_fetch_comments",
    "github_fetch_repo_structure",
    "github_fetch_docs",
    "github_fetch_ci_fixes",
    "github_fetch_code_samples",
    "github_fetch_pr_diff",
    "github_fetch_rejected_patterns",
    "github_fetch_outcome_metrics",
    "read_claude_logs",
    "store_knowledge",
    "search_knowledge",
    "list_all_knowledge",
    "delete_knowledge",
]

# MCP-prefixed tool names for allowed_tools
TOOL_NAMES = [f"mcp__{SERVER_NAME}__{name}" for name in _RAW_TOOL_NAMES]

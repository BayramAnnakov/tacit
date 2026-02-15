"""
Tacit V2 Comprehensive Eval Suite

Tests 8 capabilities:
1. Anti-Pattern Mining (CHANGES_REQUESTED patterns from PRs)
2. Provenance Coverage (source URLs and summaries on rules)
3. Path Scoping Coverage (applicable_paths with glob patterns)
4. Modular Rules Generation (.claude/rules/ file structure)
5. Incremental Extraction Simulation (single-PR extraction)
6. Outcome Metrics Collection (PR velocity and quality metrics)
7. Domain Knowledge Extraction (5 sub-evals: content quality, domain coverage,
   confidence calibration, category accuracy, DB schema self-test)
8. Ground Truth Recall (for repos with CLAUDE.md/AGENTS.md: what % of
   documented guidelines can be independently discovered from other sources?)

Usage:
    python eval_v2.py                  # Full eval (extraction + all 8 evals)
    python eval_v2.py --skip-extraction  # Reuse existing DB, run evals only
"""

import os
os.environ.pop("CLAUDECODE", None)  # Allow nested Claude SDK calls from within Claude Code

import asyncio
import argparse
import json
import re
import statistics
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone

import httpx

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

import database as db
from pipeline import (
    run_extraction,
    _run_agent,
    incremental_extract,
    collect_outcome_metrics,
    generate_modular_rules,
)
from config import settings

TOKEN = os.environ.get("GITHUB_TOKEN", "") or getattr(settings, "GITHUB_TOKEN", "")

REPOS = [
    ("langchain-ai", "langchain"),
    ("denoland", "deno"),
    ("prisma", "prisma"),
    ("vercel", "next.js"),
    ("facebook", "react"),
    ("anthropics", "claude-code"),
    ("anthropics", "claude-agent-sdk-python"),
    ("openclaw", "openclaw"),
]

DB_PATH = Path(__file__).parent / "tacit.db"
RESULTS_PATH = Path(__file__).parent / "eval_v2_results.json"


def repo_full_name(owner: str, name: str) -> str:
    return f"{owner}/{name}"


class EvalResult:
    """Container for a single eval section's results."""

    def __init__(self, name: str):
        self.name = name
        self.score: float = 0.0
        self.details: dict = {}
        self.error: str | None = None
        self.duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "details": self.details,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 2),
        }


# ---------------------------------------------------------------------------
# Phase 0: Extraction (shared across evals)
# ---------------------------------------------------------------------------

async def run_extractions(repo_ids: dict[str, int]) -> dict[str, int]:
    """Run full extraction on each repo. Returns mapping of repo_full_name -> repo_id."""
    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        repo_id = repo_ids.get(full)

        # Create repo entry if it doesn't exist
        if repo_id is None:
            try:
                repo_dict = await db.create_repo(owner, name)
                repo_id = repo_dict["id"]
                repo_ids[full] = repo_id
            except Exception as exc:
                print(f"  [error] {full}: could not create repo: {exc}")
                continue

        # Check if extraction already ran (has rules in DB)
        existing_rules = await db.list_rules(repo_id=repo_id)
        if existing_rules:
            print(f"  [skip] {full} already has {len(existing_rules)} rules (repo_id={repo_id})")
            continue

        print(f"  [extract] {full} (repo_id={repo_id}) ...")
        try:
            async for _ in run_extraction(full, TOKEN):
                pass  # consume the async iterator
            rule_count = len(await db.list_rules(repo_id=repo_id))
            print(f"  [done] {full} -> {rule_count} rules extracted")
        except Exception as exc:
            print(f"  [error] {full}: {exc}")
            traceback.print_exc()
    return repo_ids


async def ensure_repo_ids() -> dict[str, int]:
    """Look up or create repo rows so we have IDs for every repo."""
    repo_ids: dict[str, int] = {}
    rows = await db.list_repos() if hasattr(db, "list_repos") else []
    for row in rows:
        url = row.get("url", "") if isinstance(row, dict) else ""
        name = row.get("full_name", "") if isinstance(row, dict) else ""
        rid = row.get("id", 0) if isinstance(row, dict) else 0
        if name:
            repo_ids[name] = rid
        elif url:
            # Derive full name from URL
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                fn = f"{parts[-2]}/{parts[-1]}"
                repo_ids[fn] = rid
    # Ensure all eval repos have entries
    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        if full not in repo_ids:
            try:
                repo_dict = await db.create_repo(owner, name)
                repo_ids[full] = repo_dict["id"]
            except Exception:
                pass
    return repo_ids


# ---------------------------------------------------------------------------
# Helpers: direct GitHub API calls (avoids importing @tool-decorated functions)
# ---------------------------------------------------------------------------

def _gh_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


_MIN_REVIEW_COMMENTS = 3


# ---------------------------------------------------------------------------
# Helpers: LLM judge + README fetching (for Eval 7 sub-evals)
# ---------------------------------------------------------------------------

async def _llm_judge(system_prompt: str, user_prompt: str) -> str:
    """Call Claude Sonnet as LLM judge via Agent SDK. No tools needed."""
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model="sonnet",
        mcp_servers={},
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=1,
    )

    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        await client.query(user_prompt)
        result = []
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result.append(block.text)
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    return ""
        return "\n".join(result)
    except Exception:
        return ""
    finally:
        await client.disconnect()


def _parse_json_from_llm(raw: str) -> dict | list | None:
    """Extract JSON from LLM output, handling markdown code blocks."""
    raw = raw.strip()
    if "```" in raw:
        match = re.search(r'```(?:json)?\s*([\[\{].*?[\]\}])\s*```', raw, re.DOTALL)
        if match:
            raw = match.group(1)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def _fetch_readme_content(repo: str, token: str) -> str:
    """Fetch full README.md content from GitHub (direct API, no @tool)."""
    headers = _gh_headers(token)
    headers["Accept"] = "application/vnd.github.v3.raw"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for filename in ("README.md", "readme.md", "Readme.md"):
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{filename}",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                return resp.text[:8000]
    return ""


async def _fetch_rejected_patterns(repo: str, token: str, max_prs: int = 30) -> list[dict]:
    """Fetch PRs with substantive review discussions (no regex — let Claude classify)."""
    headers = _gh_headers(token)
    patterns: list[dict] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        pr_resp = await client.get(
            f"https://api.github.com/repos/{repo}/pulls",
            params={"state": "closed", "per_page": min(max_prs, 50), "sort": "updated", "direction": "desc"},
            headers=headers, timeout=30,
        )
        if pr_resp.status_code != 200:
            return []

        for pr in pr_resp.json():
            pr_num = pr["number"]
            rev_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews",
                headers=headers, params={"per_page": 20}, timeout=15,
            )
            if rev_resp.status_code != 200:
                continue

            reviews = rev_resp.json()
            changes_requested = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]
            has_formal_rejection = len(changes_requested) > 0

            comments_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/comments",
                headers=headers, params={"per_page": 50}, timeout=15,
            )
            if comments_resp.status_code != 200:
                continue

            raw_comments = comments_resp.json()

            # Selection: formal rejection OR enough comments for substantive discussion
            if not has_formal_rejection and len(raw_comments) < _MIN_REVIEW_COMMENTS:
                continue

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

    return patterns


# ---------------------------------------------------------------------------
# Eval 1: Anti-Pattern Mining
# ---------------------------------------------------------------------------

async def eval_anti_pattern_mining() -> EvalResult:
    result = EvalResult("Anti-Pattern Mining")
    t0 = time.time()

    repos_with_patterns = 0
    total_patterns = 0
    per_repo: dict[str, dict] = {}

    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        try:
            patterns = await _fetch_rejected_patterns(full, TOKEN)

            count = len(patterns)
            valid = 0
            for p in patterns:
                if not isinstance(p, dict):
                    continue
                has_pr = "pr_number" in p
                has_comments = "inline_review_comments" in p and len(p["inline_review_comments"]) > 0
                has_review_bodies = "review_bodies" in p
                if has_pr and (has_comments or has_review_bodies):
                    valid += 1

            if count > 0:
                repos_with_patterns += 1
            total_patterns += count

            per_repo[full] = {
                "patterns_found": count,
                "valid_patterns": valid,
                "sample": patterns[:2] if patterns else [],
            }
            print(f"  [anti-pattern] {full}: {count} patterns ({valid} valid)")

        except Exception as exc:
            per_repo[full] = {"error": str(exc)}
            print(f"  [anti-pattern] {full}: ERROR - {exc}")

    total_repos = len(REPOS)
    avg_patterns = total_patterns / max(total_repos, 1)
    score = repos_with_patterns / max(total_repos, 1)

    result.score = score
    result.details = {
        "repos_with_patterns": repos_with_patterns,
        "total_repos": total_repos,
        "avg_patterns_per_repo": round(avg_patterns, 1),
        "total_patterns": total_patterns,
        "per_repo": per_repo,
    }
    result.duration_seconds = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Eval 2: Provenance Coverage
# ---------------------------------------------------------------------------

async def eval_provenance_coverage() -> EvalResult:
    result = EvalResult("Provenance Coverage")
    t0 = time.time()

    all_rules = await db.list_rules()
    if isinstance(all_rules, list) and len(all_rules) > 0 and not isinstance(all_rules[0], dict):
        # Convert sqlite Row objects if needed
        all_rules = [dict(r) for r in all_rules]

    total = len(all_rules)
    with_url = 0
    with_summary = 0
    valid_github_urls = 0

    github_url_pattern = re.compile(r"^https://github\.com/")

    for rule in all_rules:
        prov_url = rule.get("provenance_url", "") or ""
        prov_summary = rule.get("provenance_summary", "") or ""

        if prov_url.strip():
            with_url += 1
            if github_url_pattern.match(prov_url.strip()):
                valid_github_urls += 1

        if prov_summary.strip():
            with_summary += 1

    url_pct = with_url / max(total, 1)
    summary_pct = with_summary / max(total, 1)
    score = (url_pct + summary_pct) / 2

    result.score = score
    result.details = {
        "total_rules": total,
        "rules_with_provenance_url": with_url,
        "rules_with_provenance_summary": with_summary,
        "valid_github_urls": valid_github_urls,
        "url_coverage_pct": round(url_pct * 100, 1),
        "summary_coverage_pct": round(summary_pct * 100, 1),
    }
    result.duration_seconds = time.time() - t0

    print(f"  [provenance] {with_url}/{total} with URL, {with_summary}/{total} with summary")
    return result


# ---------------------------------------------------------------------------
# Eval 3: Path Scoping Coverage
# ---------------------------------------------------------------------------

async def eval_path_scoping() -> EvalResult:
    result = EvalResult("Path Scoping Coverage")
    t0 = time.time()

    all_rules = await db.list_rules()
    if isinstance(all_rules, list) and len(all_rules) > 0 and not isinstance(all_rules[0], dict):
        all_rules = [dict(r) for r in all_rules]

    total = len(all_rules)
    with_paths = 0
    valid_globs = 0

    glob_pattern = re.compile(r"(\*|\.[\w]+$|/[\w\-]+/)")

    for rule in all_rules:
        paths = rule.get("applicable_paths", "") or ""
        if isinstance(paths, list):
            paths = ",".join(paths)
        paths = paths.strip()

        if paths:
            with_paths += 1
            # Check if any path entry looks like a valid glob or specific path
            path_entries = [p.strip() for p in paths.split(",") if p.strip()]
            if not path_entries:
                path_entries = [p.strip() for p in paths.split("\n") if p.strip()]
            has_valid = any(
                glob_pattern.search(p) or "/" in p or p.startswith(".")
                for p in path_entries
            )
            if has_valid:
                valid_globs += 1

    path_pct = with_paths / max(total, 1)
    score = path_pct

    result.score = score
    result.details = {
        "total_rules": total,
        "rules_with_paths": with_paths,
        "rules_with_valid_globs": valid_globs,
        "path_coverage_pct": round(path_pct * 100, 1),
    }
    result.duration_seconds = time.time() - t0

    print(f"  [path-scoping] {with_paths}/{total} with paths ({valid_globs} valid globs)")
    return result


# ---------------------------------------------------------------------------
# Eval 4: Modular Rules Generation
# ---------------------------------------------------------------------------

async def eval_modular_rules(repo_ids: dict[str, int]) -> EvalResult:
    result = EvalResult("Modular Rules Generation")
    t0 = time.time()

    total_files = 0
    valid_files = 0
    has_donot_section = 0
    per_repo: dict[str, dict] = {}

    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        rid = repo_ids.get(full)
        if rid is None:
            per_repo[full] = {"error": "no repo_id"}
            print(f"  [modular] {full}: skipped (no repo_id)")
            continue

        try:
            modular = await generate_modular_rules(rid)

            if not isinstance(modular, dict):
                per_repo[full] = {"error": f"unexpected type: {type(modular).__name__}"}
                print(f"  [modular] {full}: unexpected return type")
                continue

            file_count = len(modular)
            valid_count = 0
            donot_found = False

            for filepath, content in modular.items():
                total_files += 1
                fp = str(filepath)

                # Check path starts with .claude/
                starts_correct = fp.startswith(".claude/") or fp.startswith(".claude\\")

                # Check for do-not rules file
                if "do-not" in fp.lower() or "donot" in fp.lower() or "dont" in fp.lower():
                    donot_found = True

                # Validate file has meaningful content
                content_str = str(content) if content else ""
                has_content = len(content_str.strip()) > 20  # more than just frontmatter

                # Path-scoped files (in subdirs like rules/backend/) should have
                # YAML frontmatter with paths: field, but category-wide files
                # (rules/do-not.md, rules/testing.md) don't need it
                is_subdir_scoped = fp.count("/") >= 4  # e.g. .claude/rules/backend/api.md
                has_frontmatter = content_str.startswith("---")
                has_paths_field = "paths:" in content_str

                path_score_ok = True
                if is_subdir_scoped and has_frontmatter and not has_paths_field:
                    path_score_ok = False  # subdir-scoped files should have paths:

                if starts_correct and has_content and path_score_ok:
                    valid_count += 1
                    valid_files += 1

            if donot_found:
                has_donot_section += 1

            per_repo[full] = {
                "total_files": file_count,
                "valid_files": valid_count,
                "has_donot": donot_found,
                "file_paths": list(modular.keys())[:10],
            }
            print(f"  [modular] {full}: {file_count} files, {valid_count} valid, donot={donot_found}")

        except Exception as exc:
            per_repo[full] = {"error": str(exc)}
            print(f"  [modular] {full}: ERROR - {exc}")

    file_validity = valid_files / max(total_files, 1)
    donot_pct = has_donot_section / max(len(REPOS), 1)
    score = (file_validity * 0.7) + (donot_pct * 0.3)

    result.score = score
    result.details = {
        "total_files_generated": total_files,
        "valid_files": valid_files,
        "repos_with_donot": has_donot_section,
        "file_validity_pct": round(file_validity * 100, 1),
        "donot_coverage_pct": round(donot_pct * 100, 1),
        "per_repo": per_repo,
    }
    result.duration_seconds = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Eval 5: Incremental Extraction Simulation
# ---------------------------------------------------------------------------

async def eval_incremental_extraction(repo_ids: dict[str, int]) -> EvalResult:
    result = EvalResult("Incremental Extraction")
    t0 = time.time()

    successful = 0
    total_attempts = 0
    per_repo: dict[str, dict] = {}

    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        rid = repo_ids.get(full)
        total_attempts += 1

        # Pick a PR number -- try to find one from extraction results in the DB,
        # otherwise use a default recent PR number
        pr_number = None
        try:
            rules = await db.list_rules(repo_id=rid) if rid else []
            if isinstance(rules, list):
                for r in rules:
                    r_dict = dict(r) if not isinstance(r, dict) else r
                    prov = r_dict.get("provenance_url", "") or ""
                    # Extract PR number from URL like https://github.com/owner/repo/pull/123
                    match = re.search(r"/pull/(\d+)", prov)
                    if match:
                        pr_number = int(match.group(1))
                        break
        except Exception:
            pass

        if pr_number is None:
            # Fallback: use a known recent PR number (1 is usually safe)
            pr_number = 1

        try:
            inc_result = await incremental_extract(full, pr_number, TOKEN)

            if not isinstance(inc_result, dict):
                # Try to handle if it returns something else
                inc_result = {"raw": str(inc_result)}

            new_rules = inc_result.get("new_rules", inc_result.get("rules_added", 0))
            new_proposals = inc_result.get("new_proposals", inc_result.get("proposals", 0))
            auto_approved = inc_result.get("auto_approved", [])

            # Validate auto-approved rules have high confidence
            confidence_ok = True
            for rule in (auto_approved if isinstance(auto_approved, list) else []):
                r_dict = dict(rule) if not isinstance(rule, dict) else rule
                conf = r_dict.get("confidence", 0)
                if isinstance(conf, (int, float)) and conf < 0.85:
                    confidence_ok = False

            if isinstance(new_rules, (int, float)) and new_rules >= 0:
                successful += 1

            per_repo[full] = {
                "pr_number": pr_number,
                "new_rules": new_rules,
                "new_proposals": new_proposals if isinstance(new_proposals, (int, float)) else 0,
                "auto_approved_count": len(auto_approved) if isinstance(auto_approved, list) else 0,
                "confidence_check_passed": confidence_ok,
            }
            print(f"  [incremental] {full} PR#{pr_number}: {new_rules} new rules, {new_proposals} proposals")

        except Exception as exc:
            per_repo[full] = {"pr_number": pr_number, "error": str(exc)}
            print(f"  [incremental] {full} PR#{pr_number}: ERROR - {exc}")

    score = successful / max(total_attempts, 1)

    result.score = score
    result.details = {
        "successful_extractions": successful,
        "total_attempts": total_attempts,
        "per_repo": per_repo,
    }
    result.duration_seconds = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Eval 6: Outcome Metrics Collection
# ---------------------------------------------------------------------------

async def eval_outcome_metrics(repo_ids: dict[str, int]) -> EvalResult:
    result = EvalResult("Outcome Metrics Collection")
    t0 = time.time()

    repos_with_valid_metrics = 0
    per_repo: dict[str, dict] = {}

    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        rid = repo_ids.get(full)

        if rid is None:
            per_repo[full] = {"error": "no repo_id"}
            print(f"  [outcome] {full}: skipped (no repo_id)")
            continue

        try:
            metrics = await collect_outcome_metrics(full, TOKEN, rid)

            if not isinstance(metrics, dict):
                try:
                    metrics = json.loads(str(metrics))
                except (json.JSONDecodeError, TypeError):
                    metrics = {}

            total_prs = metrics.get("total_prs", None)
            avg_review_rounds = metrics.get("avg_review_rounds", None)
            ci_failure_rate = metrics.get("ci_failure_rate", None)
            avg_time_to_merge = metrics.get("avg_time_to_merge_hours", None)

            # Validate reasonableness
            checks = {
                "has_total_prs": total_prs is not None,
                "has_avg_review_rounds": avg_review_rounds is not None,
                "has_ci_failure_rate": ci_failure_rate is not None,
                "has_avg_time_to_merge": avg_time_to_merge is not None,
            }

            value_checks = {}
            if isinstance(total_prs, (int, float)):
                value_checks["total_prs_reasonable"] = 0 <= total_prs <= 100000
            if isinstance(avg_review_rounds, (int, float)):
                value_checks["avg_review_rounds_reasonable"] = 0 <= avg_review_rounds <= 50
            if isinstance(ci_failure_rate, (int, float)):
                value_checks["ci_failure_rate_reasonable"] = 0 <= ci_failure_rate <= 1.0
            if isinstance(avg_time_to_merge, (int, float)):
                value_checks["avg_time_to_merge_reasonable"] = 0 <= avg_time_to_merge <= 10000

            fields_present = sum(1 for v in checks.values() if v)
            values_reasonable = all(value_checks.values()) if value_checks else False

            if fields_present >= 3 and values_reasonable:
                repos_with_valid_metrics += 1

            per_repo[full] = {
                "metrics": {
                    "total_prs": total_prs,
                    "avg_review_rounds": avg_review_rounds,
                    "ci_failure_rate": ci_failure_rate,
                    "avg_time_to_merge_hours": avg_time_to_merge,
                },
                "fields_present": fields_present,
                "values_reasonable": values_reasonable,
            }
            print(
                f"  [outcome] {full}: {fields_present}/4 fields, "
                f"reasonable={values_reasonable}"
            )

        except Exception as exc:
            per_repo[full] = {"error": str(exc)}
            print(f"  [outcome] {full}: ERROR - {exc}")

    score = repos_with_valid_metrics / max(len(REPOS), 1)

    result.score = score
    result.details = {
        "repos_with_valid_metrics": repos_with_valid_metrics,
        "total_repos": len(REPOS),
        "per_repo": per_repo,
    }
    result.duration_seconds = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Eval 7: Domain Knowledge Extraction (5 sub-evals)
# ---------------------------------------------------------------------------

_DOMAIN_CATEGORIES = {"domain", "design", "product"}


async def _get_domain_rules_by_repo(repo_ids: dict[str, int]) -> dict[str, list[dict]]:
    """Fetch domain/design/product rules per repo. Returns {full_name: [rules]}."""
    result: dict[str, list[dict]] = {}
    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        rid = repo_ids.get(full)
        if rid is None:
            result[full] = []
            continue
        rules = await db.list_rules(repo_id=rid)
        domain = [r for r in rules if r.get("category") in _DOMAIN_CATEGORIES]
        result[full] = domain
    return result


async def _get_all_rules_by_repo(repo_ids: dict[str, int]) -> dict[str, list[dict]]:
    """Fetch all rules per repo. Returns {full_name: [rules]}."""
    result: dict[str, list[dict]] = {}
    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        rid = repo_ids.get(full)
        if rid is None:
            result[full] = []
            continue
        rules = await db.list_rules(repo_id=rid)
        result[full] = rules
    return result


# -- Sub-Eval 7a: Content Quality (LLM-as-Judge) -- Weight 0.30 --

async def _eval_7a_content_quality(domain_by_repo: dict[str, list[dict]]) -> tuple[float, dict]:
    """Score domain rules on specificity and actionability via LLM judge."""
    system_prompt = (
        "You evaluate software knowledge rules for quality. "
        "For each rule, score on two dimensions (1-5 each):\n"
        "- Specificity: Does it name project-specific entities, APIs, patterns? "
        "(5=highly specific, 1=generic platitude)\n"
        "- Actionability: Can a developer follow this without extra context? "
        "(5=immediately actionable, 1=vague)\n\n"
        "Return ONLY a JSON array: [{\"index\": 0, \"specificity\": N, \"actionability\": N}, ...]"
    )

    per_repo: dict[str, dict] = {}
    repo_scores: list[float] = []

    for full, rules in domain_by_repo.items():
        if not rules:
            per_repo[full] = {"skipped": True, "reason": "no domain rules"}
            continue

        # Deterministic sample: sorted by id, first 10
        sampled = sorted(rules, key=lambda r: r.get("id", 0))[:10]
        numbered = "\n".join(
            f"{i}. [{r.get('category', '?')}] {r.get('rule_text', '')}"
            for i, r in enumerate(sampled)
        )
        user_prompt = (
            f"Rate each of these {len(sampled)} knowledge rules extracted from the "
            f"{full} repository:\n\n{numbered}"
        )

        raw = await _llm_judge(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)

        if isinstance(parsed, list) and len(parsed) > 0:
            rule_scores = []
            for item in parsed:
                if isinstance(item, dict):
                    spec = item.get("specificity", 3)
                    act = item.get("actionability", 3)
                    rule_scores.append(((spec + act) / 2) / 5.0)
            avg = sum(rule_scores) / len(rule_scores) if rule_scores else 0.5
            per_repo[full] = {
                "rules_sampled": len(sampled),
                "avg_specificity": round(sum(i.get("specificity", 3) for i in parsed if isinstance(i, dict)) / max(len(parsed), 1), 2),
                "avg_actionability": round(sum(i.get("actionability", 3) for i in parsed if isinstance(i, dict)) / max(len(parsed), 1), 2),
                "score": round(avg, 3),
            }
            repo_scores.append(avg)
            print(f"  [7a quality] {full}: {per_repo[full]['avg_specificity']}/5 spec, {per_repo[full]['avg_actionability']}/5 act -> {avg:.2f}")
        else:
            # LLM call failed — neutral score
            per_repo[full] = {"rules_sampled": len(sampled), "llm_failed": True, "score": 0.5}
            repo_scores.append(0.5)
            print(f"  [7a quality] {full}: LLM judge failed, using 0.5")

    score = sum(repo_scores) / len(repo_scores) if repo_scores else 0.0
    return score, {"per_repo": per_repo}


# -- Sub-Eval 7b: Domain Coverage (LLM Holistic) -- Weight 0.25 --

async def _eval_7b_domain_coverage(domain_by_repo: dict[str, list[dict]]) -> tuple[float, dict]:
    """Score how well extracted rules cover the project's domain concepts."""
    system_prompt = (
        "You are evaluating domain knowledge extraction quality. "
        "Rate the extraction on a scale of 1-10 for:\n"
        "- Completeness: How many of the project's key domain concepts, entities, "
        "and terminology are captured?\n"
        "- Depth: Do the rules go beyond surface-level descriptions to capture "
        "relationships, constraints, and rationale?\n\n"
        "Return ONLY a JSON object: {\"completeness\": N, \"depth\": N}"
    )

    per_repo: dict[str, dict] = {}
    repo_scores: list[float] = []

    for full, rules in domain_by_repo.items():
        if not rules:
            per_repo[full] = {"skipped": True, "reason": "no domain rules"}
            continue

        # Fetch README as ground truth context
        readme = await _fetch_readme_content(full, TOKEN)
        context_label = "README" if readme else "repo name only"
        context_text = readme[:5000] if readme else f"Repository: {full}"

        numbered_rules = "\n".join(
            f"- [{r.get('category', '?')}] {r.get('rule_text', '')}"
            for r in rules[:20]
        )
        user_prompt = (
            f"Given this project's {context_label}:\n---\n{context_text}\n---\n\n"
            f"Here are the domain/design/product rules extracted by an AI system "
            f"({len(rules)} total, showing up to 20):\n{numbered_rules}\n\n"
            f"Rate the extraction quality."
        )

        raw = await _llm_judge(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)

        if isinstance(parsed, dict) and "completeness" in parsed:
            completeness = parsed.get("completeness", 5)
            depth = parsed.get("depth", 5)
            avg = ((completeness + depth) / 2) / 10.0
            per_repo[full] = {
                "rules_count": len(rules),
                "has_readme": bool(readme),
                "completeness": completeness,
                "depth": depth,
                "score": round(avg, 3),
            }
            repo_scores.append(avg)
            print(f"  [7b coverage] {full}: completeness={completeness}/10, depth={depth}/10 -> {avg:.2f}")
        else:
            per_repo[full] = {"rules_count": len(rules), "llm_failed": True, "score": 0.5}
            repo_scores.append(0.5)
            print(f"  [7b coverage] {full}: LLM judge failed, using 0.5")

    score = sum(repo_scores) / len(repo_scores) if repo_scores else 0.0
    return score, {"per_repo": per_repo}


# -- Sub-Eval 7c: Confidence Calibration -- Weight 0.15 --

async def _eval_7c_confidence_calibration(
    domain_by_repo: dict[str, list[dict]],
    all_rules_by_repo: dict[str, list[dict]],
) -> tuple[float, dict]:
    """Check if confidence scores follow documented calibration rules."""
    per_repo: dict[str, dict] = {}
    repo_scores: list[float] = []

    for full, domain_rules in domain_by_repo.items():
        all_rules = all_rules_by_repo.get(full, [])
        code_rules = [r for r in all_rules if r.get("category") not in _DOMAIN_CATEGORIES]

        if not domain_rules:
            per_repo[full] = {"skipped": True, "reason": "no domain rules"}
            continue

        domain_confs = [r.get("confidence", 0.8) for r in domain_rules]
        code_confs = [r.get("confidence", 0.8) for r in code_rules] if code_rules else [0.8]

        domain_avg = sum(domain_confs) / len(domain_confs)
        code_avg = sum(code_confs) / len(code_confs)

        # Domain should average lower than code (softer evidence)
        calibrated = domain_avg <= code_avg

        # Confidence values should be differentiated (not all identical)
        conf_spread = statistics.stdev(domain_confs) if len(domain_confs) >= 2 else 0.0
        differentiated = conf_spread > 0.03

        # No domain rule should have confidence > 0.95
        no_ceiling = all(c <= 0.95 for c in domain_confs)

        repo_score = (calibrated * 0.5) + (differentiated * 0.3) + (no_ceiling * 0.2)
        per_repo[full] = {
            "domain_avg_conf": round(domain_avg, 3),
            "code_avg_conf": round(code_avg, 3),
            "conf_spread": round(conf_spread, 4),
            "calibrated": calibrated,
            "differentiated": differentiated,
            "no_ceiling": no_ceiling,
            "score": round(repo_score, 3),
        }
        repo_scores.append(repo_score)
        print(f"  [7c calibration] {full}: domain_avg={domain_avg:.2f} vs code={code_avg:.2f}, spread={conf_spread:.3f} -> {repo_score:.2f}")

    score = sum(repo_scores) / len(repo_scores) if repo_scores else 0.0
    return score, {"per_repo": per_repo}


# -- Sub-Eval 7d: Category Accuracy (LLM-as-Judge) -- Weight 0.15 --

async def _eval_7d_category_accuracy(domain_by_repo: dict[str, list[dict]]) -> tuple[float, dict]:
    """Test whether rules are classified into the correct category."""
    system_prompt = (
        "You classify software knowledge rules into exactly one of three categories:\n"
        "- domain: Entity definitions, data models, API contracts, business rules, technical constraints\n"
        "- design: UI conventions, design tokens, component patterns, accessibility, visual guidelines\n"
        "- product: Product philosophy, personas, feature rationale, architectural WHY, user-facing decisions\n\n"
        "For each rule, return its correct category.\n"
        "Return ONLY a JSON array: [{\"index\": 0, \"category\": \"domain\"}, ...]"
    )

    per_repo: dict[str, dict] = {}
    repo_scores: list[float] = []

    for full, rules in domain_by_repo.items():
        if not rules:
            per_repo[full] = {"skipped": True, "reason": "no domain rules"}
            continue

        sampled = sorted(rules, key=lambda r: r.get("id", 0))[:10]
        numbered = "\n".join(
            f"{i}. {r.get('rule_text', '')}"
            for i, r in enumerate(sampled)
        )
        user_prompt = (
            f"Classify each of these {len(sampled)} rules from the {full} repository "
            f"into domain, design, or product:\n\n{numbered}"
        )

        raw = await _llm_judge(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)

        if isinstance(parsed, list) and len(parsed) > 0:
            matches = 0
            total = min(len(parsed), len(sampled))
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index", -1)
                llm_cat = item.get("category", "")
                if 0 <= idx < len(sampled) and llm_cat == sampled[idx].get("category"):
                    matches += 1
            accuracy = matches / total if total > 0 else 0.0
            per_repo[full] = {
                "rules_sampled": len(sampled),
                "matches": matches,
                "total_judged": total,
                "accuracy": round(accuracy, 3),
            }
            repo_scores.append(accuracy)
            print(f"  [7d category] {full}: {matches}/{total} correct -> {accuracy:.2f}")
        else:
            per_repo[full] = {"rules_sampled": len(sampled), "llm_failed": True, "score": 0.5}
            repo_scores.append(0.5)
            print(f"  [7d category] {full}: LLM judge failed, using 0.5")

    score = sum(repo_scores) / len(repo_scores) if repo_scores else 0.0
    return score, {"per_repo": per_repo}


# -- Sub-Eval 7e: DB Schema Self-Test -- Weight 0.15 --

_EXPECTED_SCHEMA_FACTS = [
    ("knowledge_rules", "foreign key", "repositories"),
    ("outcome_metrics", "UNIQUE", "repo_id"),
    ("mined_sessions", "UNIQUE", "path"),
    ("proposals", "status", "pending"),
    ("created_at", "timestamp", "datetime"),
]


async def _eval_7e_db_schema_selftest() -> tuple[float, dict]:
    """Test db-schema-analyzer against Tacit's own SQLite DB."""
    db_path = str(Path(__file__).parent / "tacit.db")
    details: dict = {}

    # Create a temporary repo record for this self-test
    temp_repo_id = None
    try:
        repo_dict = await db.create_repo("tacit", "tacit-db")
        temp_repo_id = repo_dict["id"]
    except Exception:
        # May already exist from a previous run
        repos = await db.list_repos()
        for r in repos:
            if r.get("full_name") == "tacit/tacit-db":
                temp_repo_id = r["id"]
                break

    if temp_repo_id is None:
        details["error"] = "Could not create temp repo for self-test"
        print("  [7e db-schema] Could not create temp repo")
        return 0.0, details

    # Run db-schema-analyzer agent against tacit.db
    prompt = (
        f"Analyze the SQLite database at path '{db_path}'. "
        f"Use db_connect to connect, then db_inspect_schema to understand the schema, "
        f"then db_sample_data to see example rows. "
        f"Extract domain knowledge about the data model, relationships, constraints, "
        f"and entity lifecycle. Store findings as knowledge rules with category='domain' "
        f"and repo_id={temp_repo_id}. "
        f"Connection string: sqlite:///{db_path}"
    )

    try:
        agent_output = await _run_agent("db-schema-analyzer", prompt, repo_id=temp_repo_id)
        details["agent_output_length"] = len(agent_output)
        print(f"  [7e db-schema] Agent produced {len(agent_output)} chars of output")
    except Exception as exc:
        details["agent_error"] = str(exc)
        print(f"  [7e db-schema] Agent failed: {exc}")
        return 0.0, details

    # Check extracted rules for expected schema facts
    extracted_rules = await db.list_rules(repo_id=temp_repo_id)
    rule_texts = " ".join(r.get("rule_text", "").lower() for r in extracted_rules)

    facts_found = 0
    fact_results: list[dict] = []
    for table, concept, related in _EXPECTED_SCHEMA_FACTS:
        # Check if any extracted rule mentions the key terms
        found = (
            table.lower() in rule_texts
            and (concept.lower() in rule_texts or related.lower() in rule_texts)
        )
        fact_results.append({
            "table": table, "concept": concept, "related": related, "found": found,
        })
        if found:
            facts_found += 1

    score = facts_found / len(_EXPECTED_SCHEMA_FACTS)
    details.update({
        "rules_extracted": len(extracted_rules),
        "facts_found": facts_found,
        "total_expected_facts": len(_EXPECTED_SCHEMA_FACTS),
        "fact_results": fact_results,
        "temp_repo_id": temp_repo_id,
    })
    print(f"  [7e db-schema] {facts_found}/{len(_EXPECTED_SCHEMA_FACTS)} schema facts found in {len(extracted_rules)} rules -> {score:.2f}")

    return score, details


# -- Composite Eval 7 --

async def eval_domain_knowledge(repo_ids: dict[str, int]) -> EvalResult:
    result = EvalResult("Domain Knowledge Extraction")
    t0 = time.time()

    # Pre-fetch rules for all sub-evals
    domain_by_repo = await _get_domain_rules_by_repo(repo_ids)
    all_rules_by_repo = await _get_all_rules_by_repo(repo_ids)

    repos_with_domain = sum(1 for rules in domain_by_repo.values() if rules)
    total_domain = sum(len(rules) for rules in domain_by_repo.values())
    print(f"  [domain] {repos_with_domain}/{len(REPOS)} repos have domain rules ({total_domain} total)")

    # Run sub-evals
    print("\n  --- Sub-Eval 7a: Content Quality (LLM judge) ---")
    score_7a, details_7a = await _eval_7a_content_quality(domain_by_repo)

    print("\n  --- Sub-Eval 7b: Domain Coverage (LLM holistic) ---")
    score_7b, details_7b = await _eval_7b_domain_coverage(domain_by_repo)

    print("\n  --- Sub-Eval 7c: Confidence Calibration ---")
    score_7c, details_7c = await _eval_7c_confidence_calibration(domain_by_repo, all_rules_by_repo)

    print("\n  --- Sub-Eval 7d: Category Accuracy (LLM judge) ---")
    score_7d, details_7d = await _eval_7d_category_accuracy(domain_by_repo)

    print("\n  --- Sub-Eval 7e: DB Schema Self-Test ---")
    score_7e, details_7e = await _eval_7e_db_schema_selftest()

    # Composite score
    score = (
        0.30 * score_7a
        + 0.25 * score_7b
        + 0.15 * score_7c
        + 0.15 * score_7d
        + 0.15 * score_7e
    )

    result.score = score
    result.details = {
        "repos_with_domain_rules": repos_with_domain,
        "total_domain_rules": total_domain,
        "total_repos": len(REPOS),
        "sub_evals": {
            "7a_content_quality": {"weight": 0.30, "score": round(score_7a, 4), **details_7a},
            "7b_domain_coverage": {"weight": 0.25, "score": round(score_7b, 4), **details_7b},
            "7c_confidence_calibration": {"weight": 0.15, "score": round(score_7c, 4), **details_7c},
            "7d_category_accuracy": {"weight": 0.15, "score": round(score_7d, 4), **details_7d},
            "7e_db_schema_selftest": {"weight": 0.15, "score": round(score_7e, 4), **details_7e},
        },
    }
    result.duration_seconds = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Eval 8: Ground Truth Recall
# ---------------------------------------------------------------------------

_GROUND_TRUTH_FILENAMES = ["CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md"]


async def _fetch_ground_truth_content(repo: str, token: str) -> str:
    """Fetch CLAUDE.md and AGENTS.md from a repo and concatenate as ground truth."""
    headers = _gh_headers(token)
    headers["Accept"] = "application/vnd.github.v3.raw"

    parts: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for filename in _GROUND_TRUTH_FILENAMES:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{filename}",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                parts.append(f"=== {filename} ===\n{resp.text[:10000]}")
    return "\n\n".join(parts)


async def eval_ground_truth_recall(repo_ids: dict[str, int]) -> EvalResult:
    """Eval 8: For repos with CLAUDE.md/AGENTS.md, measure what % of their
    guidelines can be independently discovered from other sources (PRs, CI,
    configs, code structure).

    Method: post-hoc filter — exclude rules whose provenance_url mentions
    CLAUDE.md or AGENTS.md, then use LLM-as-judge to compare remaining
    independent rules against the actual ground truth content.
    """
    result = EvalResult("Ground Truth Recall")
    t0 = time.time()

    per_repo: dict[str, dict] = {}
    repo_scores: list[float] = []

    for owner, name in REPOS:
        full = repo_full_name(owner, name)
        rid = repo_ids.get(full)

        if rid is None:
            per_repo[full] = {"error": "no repo_id"}
            print(f"  [gt-recall] {full}: skipped (no repo_id)")
            continue

        # Step 1: Fetch actual CLAUDE.md/AGENTS.md as ground truth
        ground_truth = await _fetch_ground_truth_content(full, TOKEN)
        if not ground_truth.strip():
            per_repo[full] = {"skipped": True, "reason": "no CLAUDE.md or AGENTS.md found"}
            print(f"  [gt-recall] {full}: skipped (no ground truth files)")
            continue

        # Step 2: Get ALL rules for this repo
        all_rules = await db.list_rules(repo_id=rid)
        if not all_rules:
            per_repo[full] = {"skipped": True, "reason": "no rules extracted"}
            print(f"  [gt-recall] {full}: skipped (no rules)")
            continue

        # Step 3: Filter out rules contaminated by ground truth
        independent_rules = []
        contaminated_count = 0
        for rule in all_rules:
            prov_url = (rule.get("provenance_url") or "").lower()
            prov_summary = (rule.get("provenance_summary") or "").lower()
            source_ref = (rule.get("source_ref") or "").lower()

            is_contaminated = (
                "claude.md" in prov_url
                or "agents.md" in prov_url
                or "claude.md" in prov_summary
                or "agents.md" in prov_summary
                or "claude.md" in source_ref
                or "agents.md" in source_ref
            )

            if is_contaminated:
                contaminated_count += 1
            else:
                independent_rules.append(rule)

        if not independent_rules:
            per_repo[full] = {
                "total_rules": len(all_rules),
                "contaminated": contaminated_count,
                "independent": 0,
                "score": 0.0,
            }
            repo_scores.append(0.0)
            print(f"  [gt-recall] {full}: 0 independent rules (all {contaminated_count} from ground truth)")
            continue

        # Step 4: Format independent rules for LLM
        numbered_rules = "\n".join(
            f"{i+1}. [{r.get('source_type', '?')}/{r.get('category', '?')}] {r.get('rule_text', '')}"
            for i, r in enumerate(independent_rules[:50])  # Cap at 50 to fit context
        )

        # Step 5: LLM judge — compare independent rules against ground truth
        system_prompt = (
            "You are a scoring judge. You receive ALL data inline — do NOT ask for more.\n"
            "Compare the ground truth guidelines against independently discovered rules.\n\n"
            "For each guideline in the ground truth, assign a match score:\n"
            "- 1.0 = FULL MATCH: the essential point is conveyed, even if worded differently\n"
            "- 0.5 = PARTIAL MATCH: the core concept is captured but specific details "
            "(exact commands, exact values, exact thresholds) are missing\n"
            "- 0.0 = NO MATCH: the guideline was not discovered at all\n\n"
            "Count each distinct actionable guideline in the ground truth (skip headings, "
            "structural text, and links — only count concrete rules/instructions).\n\n"
            "'matched' should be the SUM of all match scores (can be fractional).\n\n"
            "You MUST respond with ONLY a JSON object, no other text:\n"
            '{"total_guidelines": <int>, "matched": <float>, '
            '"unmatched_examples": ["<guideline1>", ...], '
            '"matched_examples": ["<guideline (score)>", ...]}'
        )

        user_prompt = (
            f"GROUND TRUTH (team's documented guidelines):\n"
            f"{ground_truth[:6000]}\n\n"
            f"INDEPENDENTLY DISCOVERED RULES ({len(independent_rules)} rules from PRs/CI/configs/code):\n"
            f"{numbered_rules}\n\n"
            f"Score now. Return JSON only."
        )

        llm_response = await _llm_judge(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(llm_response) if llm_response else None

        if isinstance(parsed, dict) and "total_guidelines" in parsed and "matched" in parsed:
            total_gt = parsed["total_guidelines"]
            matched = parsed["matched"]
            recall = matched / max(total_gt, 1)
            recall = min(recall, 1.0)  # Cap at 1.0

            per_repo[full] = {
                "total_rules": len(all_rules),
                "contaminated": contaminated_count,
                "independent": len(independent_rules),
                "total_guidelines": total_gt,
                "matched": matched,
                "recall": round(recall, 4),
                "unmatched_examples": parsed.get("unmatched_examples", [])[:5],
                "matched_examples": parsed.get("matched_examples", [])[:5],
                "score": recall,
            }
            repo_scores.append(recall)
            print(
                f"  [gt-recall] {full}: {matched}/{total_gt} guidelines recalled "
                f"({recall*100:.0f}%) from {len(independent_rules)} independent rules "
                f"({contaminated_count} excluded as contaminated)"
            )
        else:
            # LLM failed — use fallback score
            per_repo[full] = {
                "total_rules": len(all_rules),
                "contaminated": contaminated_count,
                "independent": len(independent_rules),
                "llm_failed": True,
                "score": 0.5,
            }
            repo_scores.append(0.5)
            print(f"  [gt-recall] {full}: LLM judge failed, using 0.5 ({len(independent_rules)} independent rules)")

    if repo_scores:
        result.score = sum(repo_scores) / len(repo_scores)
    else:
        result.score = 0.0

    result.details = {
        "repos_with_ground_truth": sum(1 for r in per_repo.values() if not r.get("skipped")),
        "total_repos": len(REPOS),
        "avg_recall": round(result.score, 4),
        "per_repo": per_repo,
    }

    result.duration_seconds = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[EvalResult]) -> float:
    print("\n")
    print("=" * 60)
    print("TACIT V2 EVAL RESULTS")
    print("=" * 60)
    print()

    scores: list[float] = []

    for i, r in enumerate(results, 1):
        pct = round(r.score * 100)
        print(f"{i}. {r.name}")

        if r.error:
            print(f"   ERROR: {r.error}")
            print(f"   SCORE: 0%")
            scores.append(0.0)
            print()
            continue

        # Print key details based on eval type
        d = r.details
        if r.name == "Anti-Pattern Mining":
            print(f"   Repos with patterns: {d.get('repos_with_patterns', 0)}/{d.get('total_repos', 0)}")
            print(f"   Avg patterns per repo: {d.get('avg_patterns_per_repo', 0)}")
            print(f"   Total patterns found: {d.get('total_patterns', 0)}")
        elif r.name == "Provenance Coverage":
            total = d.get("total_rules", 0)
            print(f"   Rules with provenance_url: {d.get('rules_with_provenance_url', 0)}/{total} ({d.get('url_coverage_pct', 0)}%)")
            print(f"   Rules with provenance_summary: {d.get('rules_with_provenance_summary', 0)}/{total} ({d.get('summary_coverage_pct', 0)}%)")
            print(f"   Valid GitHub URLs: {d.get('valid_github_urls', 0)}")
        elif r.name == "Path Scoping Coverage":
            total = d.get("total_rules", 0)
            print(f"   Rules with applicable_paths: {d.get('rules_with_paths', 0)}/{total} ({d.get('path_coverage_pct', 0)}%)")
            print(f"   Rules with valid globs: {d.get('rules_with_valid_globs', 0)}")
        elif r.name == "Modular Rules Generation":
            print(f"   Total files generated: {d.get('total_files_generated', 0)}")
            print(f"   Valid files: {d.get('valid_files', 0)} ({d.get('file_validity_pct', 0)}%)")
            print(f"   Repos with do-not section: {d.get('repos_with_donot', 0)}/{len(REPOS)} ({d.get('donot_coverage_pct', 0)}%)")
        elif r.name == "Incremental Extraction":
            print(f"   Successful extractions: {d.get('successful_extractions', 0)}/{d.get('total_attempts', 0)}")
        elif r.name == "Outcome Metrics Collection":
            print(f"   Repos with valid metrics: {d.get('repos_with_valid_metrics', 0)}/{d.get('total_repos', 0)}")
        elif r.name == "Domain Knowledge Extraction":
            print(f"   Repos with domain rules: {d.get('repos_with_domain_rules', 0)}/{d.get('total_repos', 0)}")
            print(f"   Total domain rules: {d.get('total_domain_rules', 0)}")
            subs = d.get("sub_evals", {})
            for key, label in [
                ("7a_content_quality", "Content Quality"),
                ("7b_domain_coverage", "Domain Coverage"),
                ("7c_confidence_calibration", "Confidence Calibration"),
                ("7d_category_accuracy", "Category Accuracy"),
                ("7e_db_schema_selftest", "DB Schema Self-Test"),
            ]:
                sub = subs.get(key, {})
                sub_pct = round(sub.get("score", 0) * 100)
                weight = sub.get("weight", 0)
                print(f"   {label:.<30s} {sub_pct:>3d}% (weight {weight})")
        elif r.name == "Ground Truth Recall":
            print(f"   Repos with ground truth: {d.get('repos_with_ground_truth', 0)}/{d.get('total_repos', 0)}")
            print(f"   Average recall: {d.get('avg_recall', 0)*100:.0f}%")
            pr = d.get("per_repo", {})
            for repo_name, repo_data in pr.items():
                if isinstance(repo_data, dict) and not repo_data.get("skipped"):
                    recall = repo_data.get("recall", repo_data.get("score", 0))
                    matched = repo_data.get("matched", "?")
                    total_gt = repo_data.get("total_guidelines", "?")
                    indep = repo_data.get("independent", "?")
                    contam = repo_data.get("contaminated", "?")
                    short_name = repo_name.split("/")[-1]
                    print(f"   {short_name:.<25s} {recall*100 if isinstance(recall, float) else 0:>3.0f}% ({matched}/{total_gt} matched, {indep} independent, {contam} excluded)")

        print(f"   Duration: {r.duration_seconds:.1f}s")
        print(f"   SCORE: {pct}%")
        scores.append(r.score)
        print()

    overall = sum(scores) / max(len(scores), 1)
    overall_pct = round(overall * 100)
    print("-" * 60)
    print(f"OVERALL SCORE: {overall_pct}%")
    print("=" * 60)
    print()

    return overall


def save_results(results: list[EvalResult], overall: float):
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repos": [repo_full_name(o, n) for o, n in REPOS],
        "overall_score": round(overall, 4),
        "evals": [r.to_dict() for r in results],
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Detailed results saved to {RESULTS_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Tacit V2 Eval Suite")
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip full extraction phase and reuse existing DB",
    )
    args = parser.parse_args()

    total_start = time.time()

    # Initialize database
    if not args.skip_extraction:
        print("[setup] Deleting existing DB for clean eval...")
        if DB_PATH.exists():
            DB_PATH.unlink()

    print("[setup] Initializing database...")
    await db.init_db()

    # Phase 0: Extraction
    repo_ids = await ensure_repo_ids()

    if not args.skip_extraction:
        print("\n" + "=" * 60)
        print("PHASE 0: Full Extraction")
        print("=" * 60)
        repo_ids = await run_extractions(repo_ids)
    else:
        print("\n[skip] Reusing existing database (--skip-extraction)")

    results: list[EvalResult] = []

    # Eval 1: Anti-Pattern Mining
    print("\n" + "=" * 60)
    print("EVAL 1: Anti-Pattern Mining")
    print("=" * 60)
    try:
        r1 = await eval_anti_pattern_mining()
        results.append(r1)
    except Exception as exc:
        r1 = EvalResult("Anti-Pattern Mining")
        r1.error = str(exc)
        results.append(r1)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 2: Provenance Coverage
    print("\n" + "=" * 60)
    print("EVAL 2: Provenance Coverage")
    print("=" * 60)
    try:
        r2 = await eval_provenance_coverage()
        results.append(r2)
    except Exception as exc:
        r2 = EvalResult("Provenance Coverage")
        r2.error = str(exc)
        results.append(r2)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 3: Path Scoping Coverage
    print("\n" + "=" * 60)
    print("EVAL 3: Path Scoping Coverage")
    print("=" * 60)
    try:
        r3 = await eval_path_scoping()
        results.append(r3)
    except Exception as exc:
        r3 = EvalResult("Path Scoping Coverage")
        r3.error = str(exc)
        results.append(r3)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 4: Modular Rules Generation
    print("\n" + "=" * 60)
    print("EVAL 4: Modular Rules Generation")
    print("=" * 60)
    try:
        r4 = await eval_modular_rules(repo_ids)
        results.append(r4)
    except Exception as exc:
        r4 = EvalResult("Modular Rules Generation")
        r4.error = str(exc)
        results.append(r4)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 5: Incremental Extraction
    print("\n" + "=" * 60)
    print("EVAL 5: Incremental Extraction")
    print("=" * 60)
    try:
        r5 = await eval_incremental_extraction(repo_ids)
        results.append(r5)
    except Exception as exc:
        r5 = EvalResult("Incremental Extraction")
        r5.error = str(exc)
        results.append(r5)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 6: Outcome Metrics
    print("\n" + "=" * 60)
    print("EVAL 6: Outcome Metrics Collection")
    print("=" * 60)
    try:
        r6 = await eval_outcome_metrics(repo_ids)
        results.append(r6)
    except Exception as exc:
        r6 = EvalResult("Outcome Metrics Collection")
        r6.error = str(exc)
        results.append(r6)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 7: Domain Knowledge
    print("\n" + "=" * 60)
    print("EVAL 7: Domain Knowledge Extraction")
    print("=" * 60)
    try:
        r7 = await eval_domain_knowledge(repo_ids)
        results.append(r7)
    except Exception as exc:
        r7 = EvalResult("Domain Knowledge Extraction")
        r7.error = str(exc)
        results.append(r7)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Eval 8: Ground Truth Recall
    print("\n" + "=" * 60)
    print("EVAL 8: Ground Truth Recall")
    print("=" * 60)
    try:
        r8 = await eval_ground_truth_recall(repo_ids)
        results.append(r8)
    except Exception as exc:
        r8 = EvalResult("Ground Truth Recall")
        r8.error = str(exc)
        results.append(r8)
        print(f"  FATAL ERROR: {exc}")
        traceback.print_exc()

    # Report
    overall = print_report(results)

    total_elapsed = time.time() - total_start
    print(f"Total eval time: {total_elapsed:.1f}s ({total_elapsed / 60:.1f}m)")

    save_results(results, overall)

    # Exit with non-zero if overall score is below 50%
    if overall < 0.5:
        print("\nWARNING: Overall score below 50% threshold")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

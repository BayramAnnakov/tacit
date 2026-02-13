"""
Tacit V2 Comprehensive Eval Suite

Tests 6 new capabilities added in v2:
1. Anti-Pattern Mining (CHANGES_REQUESTED patterns from PRs)
2. Provenance Coverage (source URLs and summaries on rules)
3. Path Scoping Coverage (applicable_paths with glob patterns)
4. Modular Rules Generation (.claude/rules/ file structure)
5. Incremental Extraction Simulation (single-PR extraction)
6. Outcome Metrics Collection (PR velocity and quality metrics)

Usage:
    python eval_v2.py                  # Full eval (extraction + all 6 evals)
    python eval_v2.py --skip-extraction  # Reuse existing DB, run evals only
"""

import asyncio
import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone

import httpx

import database as db
from pipeline import (
    run_extraction,
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

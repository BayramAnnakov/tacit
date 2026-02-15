"""CLI entry point: python -m tacit owner/repo

Zero-config single-command knowledge extraction.
Runs the full pipeline and prints CLAUDE.md to stdout.

Usage:
    python -m tacit owner/repo                  # Extract + print CLAUDE.md
    python -m tacit owner/repo --modular        # Extract + print .claude/rules/ files
    python -m tacit owner/repo --output dir/    # Extract + write files to directory
    python -m tacit owner/repo --skip-extract   # Reuse existing DB, just generate
"""

import os
os.environ.pop("CLAUDECODE", None)  # Allow nested Claude SDK calls

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure the backend directory is on the path (for imports when run as module)
sys.path.insert(0, str(Path(__file__).parent))

import database as db
from config import settings
from pipeline import run_extraction, generate_claude_md, generate_modular_rules


BANNER = """\033[1;36m
  ╔╦╗┌─┐┌─┐┬┌┬┐
   ║ ├─┤│  │ │
   ╩ ┴ ┴└─┘┴ ┴
\033[0m\033[90m  Continuous team knowledge extraction\033[0m
"""


def _progress(msg: str) -> None:
    """Print a progress message to stderr (keeps stdout clean for output)."""
    print(f"\033[90m  → {msg}\033[0m", file=sys.stderr)


def _error(msg: str) -> None:
    print(f"\033[31m  ✗ {msg}\033[0m", file=sys.stderr)


def _success(msg: str) -> None:
    print(f"\033[32m  ✓ {msg}\033[0m", file=sys.stderr)


async def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tacit",
        description="Extract team knowledge from a GitHub repo and generate CLAUDE.md",
    )
    parser.add_argument(
        "repo",
        help="GitHub repository in owner/repo format (e.g. anthropics/claude-code)",
    )
    parser.add_argument(
        "--modular",
        action="store_true",
        help="Generate .claude/rules/ directory structure instead of monolithic CLAUDE.md",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Write output to directory instead of stdout",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip extraction, just generate from existing knowledge base",
    )
    parser.add_argument(
        "--max-prs",
        type=int,
        default=20,
        help="Maximum PRs to analyze (default: 20, was 10 in v2)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (useful for programmatic consumption)",
    )
    args = parser.parse_args()

    # Validate repo format
    if "/" not in args.repo:
        _error(f"Invalid repo format: {args.repo}")
        _error("Expected: owner/repo (e.g. anthropics/claude-code)")
        return 1

    # Check required env vars
    github_token = settings.GITHUB_TOKEN or os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        _error("GITHUB_TOKEN not set. Export it or add to .env file.")
        return 1

    if not settings.ANTHROPIC_API_KEY and not os.environ.get("ANTHROPIC_API_KEY", ""):
        _error("ANTHROPIC_API_KEY not set. Export it or add to .env file.")
        return 1

    print(BANNER, file=sys.stderr)
    _progress(f"Target: {args.repo}")

    # Init database
    await db.init_db()

    # Find or create repo record
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == args.repo:
            repo_record = r
            break

    if repo_record:
        repo_id = repo_record["id"]
        existing_rules = await db.list_rules(repo_id=repo_id)
        _progress(f"Found existing repo (id={repo_id}, {len(existing_rules)} rules)")
    else:
        repo_id = None  # Will be created during extraction

    # Run extraction unless skipped
    if not args.skip_extract:
        _progress("Starting extraction pipeline...")
        rules_found = 0
        async for event in run_extraction(args.repo, github_token, max_prs=args.max_prs):
            if event.event_type == "stage_change":
                _progress(event.message)
            elif event.event_type == "rules_found":
                rules_found = event.data.get("total", 0) if event.data else 0
            elif event.event_type == "error":
                _error(event.message)
            elif event.event_type == "complete":
                rules_found = event.data.get("total_rules", 0) if event.data else rules_found
                _success(f"Extraction complete: {rules_found} rules found")

        # Re-fetch repo_id after extraction (may have been created)
        repos = await db.list_repos()
        for r in repos:
            if r["full_name"] == args.repo:
                repo_id = r["id"]
                break
    elif repo_id is None:
        _error(f"Repo {args.repo} not found in database. Run without --skip-extract first.")
        return 1

    # Generate output — repo_id is guaranteed non-None at this point
    assert repo_id is not None
    if args.modular:
        _progress("Generating modular .claude/rules/ files...")
        files = await generate_modular_rules(repo_id, fast=True)

        if not files:
            _error("No modular rules generated.")
            return 1

        _success(f"Generated {len(files)} rule files")

        if args.output:
            # Write files to output directory
            out_dir = Path(args.output)
            for filepath, content in files.items():
                full_path = out_dir / filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)
                _progress(f"  Wrote {filepath}")
            _success(f"Output written to {out_dir}/")
        elif args.json_output:
            print(json.dumps({"repo": args.repo, "files": files}, indent=2))
        else:
            # Print each file to stdout with separators
            for filepath, content in sorted(files.items()):
                print(f"\n{'='*60}")
                print(f"# {filepath}")
                print(f"{'='*60}")
                print(content)
    else:
        _progress("Generating CLAUDE.md...")
        claude_md = await generate_claude_md(repo_id, fast=True)

        if not claude_md.strip():
            _error("No CLAUDE.md content generated.")
            return 1

        line_count = len(claude_md.strip().splitlines())
        _success(f"Generated CLAUDE.md ({line_count} lines)")

        if args.output:
            out_path = Path(args.output)
            if out_path.is_dir():
                out_path = out_path / "CLAUDE.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(claude_md)
            _success(f"Written to {out_path}")
        elif args.json_output:
            print(json.dumps({"repo": args.repo, "claude_md": claude_md}))
        else:
            print(claude_md)

    # Print summary stats to stderr
    final_rules = await db.list_rules(repo_id=repo_id)
    total = len(final_rules)
    if total > 0:
        anti_patterns = sum(1 for r in final_rules if r.get("source_type") == "anti_pattern")
        with_provenance = sum(1 for r in final_rules if r.get("provenance_url"))
        novel = sum(1 for r in final_rules if r.get("source_type") not in ("docs", "conversation"))
        print(f"\n\033[1m  Summary: {total} rules | {novel} novel ({round(novel*100/total)}%) | {anti_patterns} anti-patterns | {with_provenance} with provenance\033[0m", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

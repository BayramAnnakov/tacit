"""CLI entry point: tacit owner/repo

Zero-config single-command knowledge extraction.
Runs the full pipeline and prints CLAUDE.md to stdout.

Usage:
    tacit owner/repo                        # Extract + print CLAUDE.md
    tacit owner/repo --demo                 # Demo mode (no API keys needed)
    tacit owner/repo --modular              # Extract + print .claude/rules/ files
    tacit owner/repo --output dir/          # Extract + write files to directory
    tacit owner/repo --skip-extract         # Reuse existing DB, just generate
    tacit owner/repo --skip-extract --summary  # Quick stats + top rules
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


def _link(url: str, text: str) -> str:
    """OSC 8 clickable hyperlink (works in iTerm2, Ghostty, WezTerm, etc.)."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def _print_cost(cost_data: dict) -> None:
    """Print pipeline cost and timing breakdown to stderr."""
    if not cost_data:
        return
    if not (cost_data.get("total_cost_usd", 0) > 0 or cost_data.get("elapsed_seconds", 0) > 0):
        return

    parts = []

    # Timing
    elapsed = cost_data.get("elapsed_seconds", 0)
    if elapsed > 0:
        if elapsed >= 60:
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            parts.append(f"{mins}m{secs}s")
        else:
            parts.append(f"{int(elapsed)}s")

    # Agent count
    num_agents = cost_data.get("num_agents_run", 0)
    if num_agents > 0:
        parts.append(f"{num_agents} agent runs")

    # Token usage
    input_t = cost_data.get("total_input_tokens", 0)
    output_t = cost_data.get("total_output_tokens", 0)
    cache_t = cost_data.get("total_cache_read_tokens", 0)
    if input_t or output_t:
        token_str = f"{input_t + output_t:,} tokens"
        if cache_t:
            token_str += f" ({cache_t:,} cached)"
        parts.append(token_str)

    # Cost
    total_cost = cost_data.get("total_cost_usd", 0)
    if total_cost > 0:
        cost_str = f"${total_cost:.2f}"
        by_model = cost_data.get("by_model", {})
        if len(by_model) > 1:
            model_parts = []
            for model, model_cost in sorted(by_model.items(), key=lambda x: x[1], reverse=True):
                model_parts.append(f"{model}: ${model_cost:.2f}")
            cost_str += f" ({', '.join(model_parts)})"
        parts.append(cost_str)

    if parts:
        print(f"\033[90m  Pipeline: {' | '.join(parts)}\033[0m", file=sys.stderr)


# Generic patterns found in any codebase — deprioritize for demo display
_GENERIC_LOWTEXT = [
    "without test coverage", "without updating its corresponding tests",
    "commented-out code or dead", "dead/debugging code",
    "relative paths for file i/o",
    "code comments that contradict",
    "duplicate regex patterns, constants",
]


def _novelty_score(rule: dict) -> float:
    """Score how novel/specific a rule is. Higher = more compelling for demo."""
    text = rule.get("rule_text", "").lower()
    score = rule.get("confidence", 0.5)

    # Penalize generic rules any project would have
    for pat in _GENERIC_LOWTEXT:
        if pat in text:
            score *= 0.4
            break

    # Boost rules mentioning project-specific entities/APIs
    specifics = [
        "pnpm", "discord", "carbon", "typebox", "zod", "rawmember",
        "context_tokens", "output_tokens", "context window",
        "cached promise", "singleton", "crypto", "key rotation",
        "1000 loc", "file size gate",
        "a2a policy", "agent-to-agent", "self-call",
        "changelog", "compute and discard",
        "accept `unknown`", "static_asset", "spa fallback",
        "lazy singleton", "cached promise",
    ]

    # Deprioritize rules about human workflow decisions (not coding patterns)
    workflow_design = [
        "emoji reaction", "auto-close", "auto-closure",
        "before opening a new pr",
        "coordinate with existing pr",
    ]
    for pat in workflow_design:
        if pat in text:
            score *= 0.5
            break
    for term in specifics:
        if term in text:
            score *= 1.4
            break

    return score


def _print_summary(rules: list[dict], repo_name: str) -> None:
    """Print concise summary: stats + anti-pattern/do-not rules only."""
    total = len(rules)
    novel = sum(1 for r in rules if r.get("source_type") not in ("docs", "conversation"))
    anti = sum(1 for r in rules if r.get("source_type") == "anti_pattern")
    prov = sum(1 for r in rules if r.get("provenance_url"))
    by_source: dict[str, int] = {}
    for r in rules:
        st = r.get("source_type", "unknown")
        by_source[st] = by_source.get(st, 0) + 1

    docs_count = by_source.get("docs", 0) + by_source.get("config", 0)
    discovered = anti + by_source.get("pr", 0) + by_source.get("ci_fix", 0)

    print(f"\033[1;36m  {repo_name}\033[0m")
    print(f"\033[1m  {total} rules extracted | {novel} novel ({round(novel*100/total)}%) | {prov} with provenance\033[0m")
    print(f"\033[90m  {discovered} discovered from PRs & CI | {docs_count} from docs & config\033[0m")
    print()

    # Helper to format a rule for display
    def _fmt_rule(r: dict) -> tuple[str, str]:
        text = r["rule_text"]
        if ". " in text:
            text = text[:text.index(". ") + 1]
        if len(text) > 120:
            text = text[:117] + "..."
        prov_url = r.get("provenance_url", "")
        pr_ref = ""
        if prov_url and "/pull/" in prov_url:
            pr_num = prov_url.split("/pull/")[-1].split("#")[0]
            pr_ref = f" \033[90m({_link(prov_url, f'PR #{pr_num}')})\033[0m"
        return text, pr_ref

    # Show anti-pattern rules — sorted by novelty, max 2 per PR
    anti_rules = [r for r in rules if r.get("source_type") == "anti_pattern"]
    if anti_rules:
        ranked = sorted(anti_rules, key=_novelty_score, reverse=True)
        shown: list[dict] = []
        pr_counts: dict[str, int] = {}
        for r in ranked:
            p = r.get("provenance_url", "")
            pr_id = p.split("/pull/")[-1] if "/pull/" in p else None
            if pr_id:
                pr_counts[pr_id] = pr_counts.get(pr_id, 0) + 1
                if pr_counts[pr_id] > 2:
                    continue
            shown.append(r)
            if len(shown) >= 5:
                break
        print(f"\033[1;31m  Anti-Patterns ({len(anti_rules)} rules, showing top {len(shown)}):\033[0m")
        for r in shown:
            text, pr_ref = _fmt_rule(r)
            print(f"  \033[31m  ✗\033[0m {text}{pr_ref}")
        print()

    # Show novel PR-derived rules — sorted by novelty, dedup by PR
    pr_rules = [r for r in rules if r.get("source_type") == "pr"]
    if pr_rules:
        ranked = sorted(pr_rules, key=_novelty_score, reverse=True)
        shown_pr: list[dict] = []
        seen_prs: set[str] = set()
        for r in ranked:
            p = r.get("provenance_url", "")
            pr_id = p.split("/pull/")[-1] if "/pull/" in p else None
            if pr_id and pr_id in seen_prs:
                continue
            if pr_id:
                seen_prs.add(pr_id)
            shown_pr.append(r)
            if len(shown_pr) >= 5:
                break
        print(f"\033[1;33m  PR-Derived Rules ({len(pr_rules)} rules, showing top {len(shown_pr)}):\033[0m")
        for r in shown_pr:
            text, pr_ref = _fmt_rule(r)
            print(f"  \033[33m  →\033[0m {text}{pr_ref}")
        print()

    # Show CI-fix rules — sorted by novelty
    ci_rules = [r for r in rules if r.get("source_type") == "ci_fix"]
    if ci_rules:
        ranked = sorted(ci_rules, key=_novelty_score, reverse=True)
        print(f"\033[1;32m  CI-Fix Rules ({len(ci_rules)} rules, showing top 5):\033[0m")
        for r in ranked[:5]:
            text, pr_ref = _fmt_rule(r)
            print(f"  \033[32m  ✓\033[0m {text}{pr_ref}")
        print()


async def _run_demo(repo_name: str) -> int:
    """Demo mode: seed data, simulate extraction, show summary. No API keys needed."""
    from demo_data import seed_demo_rules, run_simulated_extraction, DEMO_COST_DATA

    print(BANNER, file=sys.stderr)
    print(f"\033[1;35m  [Demo Mode]\033[0m \033[90mUsing pre-loaded data for {repo_name}\033[0m", file=sys.stderr)
    print(file=sys.stderr)

    # Init DB and create/find repo
    await db.init_db()
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == repo_name:
            repo_record = r
            break

    if repo_record:
        repo_id = repo_record["id"]
        existing = await db.list_rules(repo_id=repo_id)
        if not existing:
            # Repo exists but no rules — seed demo data
            await seed_demo_rules(repo_id)
        rules = await db.list_rules(repo_id=repo_id)
    else:
        # Create repo and seed
        owner, name = repo_name.split("/", 1)
        record = await db.create_repo(owner, name)
        repo_id = record["id"]
        await seed_demo_rules(repo_id)
        rules = await db.list_rules(repo_id=repo_id)

    # Always show the extraction animation — it's the whole point of demo mode
    await run_simulated_extraction(len(rules))

    print(file=sys.stderr)
    _print_summary(rules, repo_name)
    _print_cost(DEMO_COST_DATA)
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tacit",
        description="Extract team knowledge from a GitHub repo and generate CLAUDE.md",
    )
    parser.add_argument(
        "repo",
        help="GitHub repository in owner/repo format (e.g. anthropics/claude-code)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demo mode: use pre-loaded data, no API keys needed",
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
        default=50,
        help="Maximum PRs to analyze (default: 50)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (useful for programmatic consumption)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show concise summary: stats + do-not rules only",
    )
    args = parser.parse_args()

    # Validate repo format
    if "/" not in args.repo:
        _error(f"Invalid repo format: {args.repo}")
        _error("Expected: owner/repo (e.g. anthropics/claude-code)")
        return 1

    # Demo mode — no API keys needed
    if args.demo:
        return await _run_demo(args.repo)

    # Check required env vars (only for real extraction)
    github_token = settings.GITHUB_TOKEN or os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        _error("GITHUB_TOKEN not set. Export it or add to .env file.")
        _error("Hint: use --demo for a quick demo without API keys")
        return 1

    if not settings.ANTHROPIC_API_KEY and not os.environ.get("ANTHROPIC_API_KEY", ""):
        _error("ANTHROPIC_API_KEY not set. Export it or add to .env file.")
        _error("Hint: use --demo for a quick demo without API keys")
        return 1

    # Lazy import — pipeline requires claude-agent-sdk
    from pipeline import run_extraction, generate_claude_md, generate_modular_rules

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
    cost_data: dict = {}
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
                cost_data = event.data.get("cost", {}) if event.data else {}
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

    if args.summary:
        rules = await db.list_rules(repo_id=repo_id)
        _print_summary(rules, args.repo)
        _print_cost(cost_data)
        return 0

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

    _print_cost(cost_data)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

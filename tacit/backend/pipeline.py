"""Extraction pipeline orchestrator using Claude Agent SDK."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from agents import get_agent_definitions
from tools import create_tacit_tools_server, TOOL_NAMES, SERVER_NAME
from config import settings
from models import ExtractionEvent
import database as db

logger = logging.getLogger(__name__)


async def _run_agent(
    agent_name: str,
    prompt: str,
    repo_id: int | None = None,
) -> str:
    """Run a single agent and collect its text output."""
    agents = get_agent_definitions()
    tools_server = create_tacit_tools_server()

    options = ClaudeAgentOptions(
        system_prompt=agents[agent_name].prompt,
        model=agents[agent_name].model,
        mcp_servers={SERVER_NAME: tools_server},
        allowed_tools=TOOL_NAMES,
        permission_mode="bypassPermissions",
        max_turns=20,
    )

    result_text = []
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text.append(block.text)
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    logger.error(f"Agent {agent_name} error: {message.result}")
    finally:
        await client.disconnect()

    return "\n".join(result_text)


async def run_extraction(repo: str, github_token: str) -> AsyncIterator[ExtractionEvent]:
    """Orchestrate the multi-source extraction pipeline.

    Phase 1: Parallel data gathering (structural, docs, CI fixes)
    Phase 2: PR analysis (scanner → thread analyzer per PR)
    Phase 3: Await parallel tasks
    Phase 4: Synthesize across ALL sources
    Phase 5: (optional) Generator can be called separately via /api/claude-md

    Yields ExtractionEvent objects for real-time streaming to the frontend.
    """
    # Find or create repo record
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == repo:
            repo_record = r
            break

    if not repo_record:
        owner, name = repo.split("/", 1)
        repo_record = await db.create_repo(owner, name)

    repo_id = repo_record["id"]
    run = await db.create_extraction_run(repo_id)
    run_id = run["id"]

    try:
        # === Phase 1: Launch parallel analyzers ===
        yield ExtractionEvent(
            event_type="stage_change",
            stage="repo_analysis",
            message=f"Analyzing repository structure, docs, and CI patterns for {repo}...",
        )
        await db.update_extraction_run(run_id, stage="repo_analysis")

        # Launch structural, docs, and CI analysis in parallel
        structural_task = asyncio.create_task(
            _run_structural_analysis(repo, github_token, repo_id)
        )
        docs_task = asyncio.create_task(
            _run_docs_analysis(repo, github_token, repo_id)
        )
        ci_fixes_task = asyncio.create_task(
            _run_ci_failure_mining(repo, github_token, repo_id)
        )
        code_analysis_task = asyncio.create_task(
            _run_code_analysis(repo, github_token, repo_id)
        )

        yield ExtractionEvent(
            event_type="progress",
            stage="repo_analysis",
            message="Launched parallel analysis: repo structure, docs, CI failures, code analysis",
            data={"parallel_tasks": ["structural", "docs", "ci_fixes", "code_analysis"]},
        )

        # === Phase 2: PR analysis (sequential, existing flow) ===
        yield ExtractionEvent(
            event_type="stage_change",
            stage="scanning",
            message=f"Scanning PRs in {repo} for knowledge-rich discussions...",
        )
        await db.update_extraction_run(run_id, stage="scanning")

        scanner_prompt = (
            f"Scan the GitHub repository '{repo}' for knowledge-rich pull requests. "
            f"Use the github_fetch_prs tool with github_token='{github_token}', repo='{repo}', per_page=50. "
            f"Prioritize first-timer PRs and PRs with CHANGES_REQUESTED reviews. "
            f"Return the top 10 most promising PRs as JSON."
        )
        scanner_result = await _run_agent("pr-scanner", scanner_prompt, repo_id)

        # Parse PR numbers from scanner output
        pr_numbers = _parse_pr_numbers(scanner_result)

        yield ExtractionEvent(
            event_type="progress",
            stage="scanning",
            message=f"Found {len(pr_numbers)} knowledge-rich PRs",
            data={"pr_count": len(pr_numbers)},
        )

        # Analyze each PR thread
        yield ExtractionEvent(
            event_type="stage_change",
            stage="analyzing",
            message="Analyzing PR discussion threads...",
        )
        await db.update_extraction_run(run_id, stage="analyzing")

        # Analyze PR threads in parallel (up to 3 concurrent)
        sem = asyncio.Semaphore(3)
        pr_tasks = []
        for pr_num in pr_numbers[:10]:
            task = asyncio.create_task(
                _analyze_single_pr(sem, repo, github_token, repo_id, pr_num)
            )
            pr_tasks.append((pr_num, task))

        yield ExtractionEvent(
            event_type="progress",
            stage="analyzing",
            message=f"Analyzing {len(pr_tasks)} PRs (3 concurrent)...",
            data={"pr_count": len(pr_tasks)},
        )

        # Wait for all PR analyses to complete
        results = await asyncio.gather(
            *[t for _, t in pr_tasks],
            return_exceptions=True,
        )

        # Report results
        for (pr_num, _), result in zip(pr_tasks, results):
            if isinstance(result, Exception):
                logger.warning(f"PR #{pr_num} analysis failed: {result}")

        # Count rules after all PR analyses
        rules = await db.list_rules(repo_id=repo_id)
        rules_found = len(rules)

        yield ExtractionEvent(
            event_type="rule_found",
            stage="analyzing",
            message=f"PR analysis complete: {rules_found} rules found",
            data={"total_rules": rules_found},
        )

        await db.update_extraction_run(run_id, prs_analyzed=len(pr_tasks), rules_found=rules_found)

        # === Phase 3: Await parallel tasks ===
        yield ExtractionEvent(
            event_type="progress",
            stage="analyzing",
            message="Waiting for parallel analysis tasks to complete...",
        )

        parallel_results = await asyncio.gather(
            structural_task, docs_task, ci_fixes_task, code_analysis_task,
            return_exceptions=True,
        )

        # Report parallel task results
        task_names = ["Structural analysis", "Docs analysis", "CI failure mining", "Code analysis"]
        for name, result in zip(task_names, parallel_results):
            if isinstance(result, Exception):
                logger.warning(f"{name} failed: {result}")
                yield ExtractionEvent(
                    event_type="progress",
                    stage="analyzing",
                    message=f"{name} encountered an error (non-fatal): {str(result)[:100]}",
                )
            else:
                yield ExtractionEvent(
                    event_type="progress",
                    stage="analyzing",
                    message=f"{name} completed successfully",
                )

        # Update rule count after parallel tasks
        all_rules = await db.list_rules(repo_id=repo_id)
        rules_found = len(all_rules)

        yield ExtractionEvent(
            event_type="progress",
            stage="analyzing",
            message=f"All sources analyzed: {rules_found} total rules before synthesis",
            data={"total_rules": rules_found},
        )

        # === Phase 4: Synthesize across ALL sources ===
        yield ExtractionEvent(
            event_type="stage_change",
            stage="synthesizing",
            message="Synthesizing rules across all sources (PRs, structure, docs, CI fixes)...",
        )
        await db.update_extraction_run(run_id, stage="synthesizing")

        synth_prompt = (
            f"Synthesize all knowledge rules for repo_id={repo_id}. "
            f"Rules come from multiple sources: pr, structure, docs, ci_fix. "
            f"Apply cross-source prioritization (ci_fix > structure/docs > pr), "
            f"boost confidence for rules confirmed across sources, "
            f"merge duplicates, and remove generic/low-quality rules."
        )
        await _run_agent("synthesizer", synth_prompt, repo_id)

        final_rules = await db.list_rules(repo_id=repo_id)
        await db.update_extraction_run(
            run_id,
            status="completed",
            stage="complete",
            rules_found=len(final_rules),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Count rules by source type for reporting
        source_counts: dict[str, int] = {}
        for rule in final_rules:
            st = rule.get("source_type", "unknown")
            source_counts[st] = source_counts.get(st, 0) + 1

        yield ExtractionEvent(
            event_type="complete",
            stage="complete",
            message=f"Extraction complete: {len(final_rules)} rules from {len(pr_numbers[:10])} PRs + structure + docs + CI fixes",
            data={
                "total_rules": len(final_rules),
                "prs_analyzed": len(pr_numbers[:10]),
                "rules_by_source": source_counts,
            },
        )

    except Exception as e:
        logger.exception(f"Extraction pipeline error: {e}")
        await db.update_extraction_run(run_id, status="failed", stage="error")
        yield ExtractionEvent(
            event_type="error",
            stage="error",
            message=f"Extraction failed: {str(e)}",
        )


async def _analyze_single_pr(
    sem: asyncio.Semaphore,
    repo: str,
    github_token: str,
    repo_id: int,
    pr_num: int,
) -> str:
    """Analyze a single PR with semaphore-limited concurrency."""
    async with sem:
        analyzer_prompt = (
            f"Analyze PR #{pr_num} in repository '{repo}'. "
            f"Use github_fetch_comments with repo='{repo}', pr_number={pr_num}, github_token='{github_token}'. "
            f"Extract knowledge rules and store them using store_knowledge with repo_id={repo_id}."
        )
        return await _run_agent("thread-analyzer", analyzer_prompt, repo_id)


async def _run_structural_analysis(repo: str, github_token: str, repo_id: int) -> str:
    """Run the structural analyzer agent."""
    prompt = (
        f"Analyze the structure of repository '{repo}'. "
        f"Use github_fetch_repo_structure with repo='{repo}', github_token='{github_token}'. "
        f"Extract conventions from the file tree, commit messages, and branch rulesets. "
        f"Store each convention using store_knowledge with source_type='structure' and repo_id={repo_id}."
    )
    return await _run_agent("structural-analyzer", prompt, repo_id)


async def _run_docs_analysis(repo: str, github_token: str, repo_id: int) -> str:
    """Run the docs analyzer agent."""
    prompt = (
        f"Analyze the contributing documentation of repository '{repo}'. "
        f"Use github_fetch_docs with repo='{repo}', github_token='{github_token}'. "
        f"Extract conventions from CONTRIBUTING.md, README setup sections, and any CLAUDE.md/AGENTS.md. "
        f"Store each convention using store_knowledge with source_type='docs' and repo_id={repo_id}."
    )
    return await _run_agent("docs-analyzer", prompt, repo_id)


async def _run_ci_failure_mining(repo: str, github_token: str, repo_id: int) -> str:
    """Run the CI failure miner agent."""
    prompt = (
        f"Mine CI failure-to-fix patterns from repository '{repo}'. "
        f"Use github_fetch_ci_fixes with repo='{repo}', github_token='{github_token}'. "
        f"For each CI failure that was fixed, extract the implicit convention. "
        f"Store each convention using store_knowledge with source_type='ci_fix' and repo_id={repo_id}."
    )
    return await _run_agent("ci-failure-miner", prompt, repo_id)


async def _run_code_analysis(repo: str, github_token: str, repo_id: int) -> str:
    """Run the code analyzer agent."""
    prompt = (
        f"Analyze configuration files and code samples from repository '{repo}'. "
        f"Use github_fetch_code_samples with repo='{repo}', github_token='{github_token}'. "
        f"Extract conventions from test configs, linter configs, CI workflows, and package configs. "
        f"Store each convention using store_knowledge with source_type='config' and repo_id={repo_id}."
    )
    return await _run_agent("code-analyzer", prompt, repo_id)


def _parse_pr_numbers(scanner_result: str) -> list[int]:
    """Parse PR numbers from scanner output, with fallback."""
    pr_numbers = []
    try:
        for line in scanner_result.split("\n"):
            line = line.strip()
            if line.startswith("["):
                data = json.loads(line)
                pr_numbers = [item["pr_number"] for item in data if "pr_number" in item]
                break
        if not pr_numbers:
            data = json.loads(scanner_result)
            if isinstance(data, list):
                pr_numbers = [item["pr_number"] for item in data if "pr_number" in item]
    except (json.JSONDecodeError, KeyError):
        logger.warning("Could not parse PR numbers from scanner output, using top 5 PRs")
        pr_numbers = list(range(1, 6))
    return pr_numbers


async def run_local_extraction(project_path: str) -> AsyncIterator[ExtractionEvent]:
    """Extract knowledge from local Claude Code conversation logs."""
    yield ExtractionEvent(
        event_type="stage_change",
        stage="local_extraction",
        message=f"Extracting knowledge from local logs: {project_path}",
    )

    extractor_prompt = (
        f"Extract knowledge rules from Claude Code conversation logs for project at '{project_path}'. "
        f"Use read_claude_logs to access the logs, then use store_knowledge to save each rule. "
        f"Use source_type='conversation' and source_ref='local-logs:{project_path}'."
    )

    try:
        result = await _run_agent("local-extractor", extractor_prompt)

        rules = await db.search_rules(query_text=project_path)
        yield ExtractionEvent(
            event_type="complete",
            stage="complete",
            message=f"Local extraction complete: found {len(rules)} rules",
            data={"total_rules": len(rules)},
        )
    except Exception as e:
        logger.exception(f"Local extraction error: {e}")
        yield ExtractionEvent(
            event_type="error",
            stage="error",
            message=f"Local extraction failed: {str(e)}",
        )


async def run_single_pr_extraction(repo: str, pr_number: int, github_token: str) -> int:
    """Extract knowledge from a single PR (used by webhook). Returns count of new proposals."""
    # Find repo record
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == repo:
            repo_record = r
            break

    if not repo_record:
        logger.warning(f"Repo {repo} not found for single PR extraction")
        return 0

    repo_id = repo_record["id"]

    # Count existing rules before
    existing_rules = await db.list_rules(repo_id=repo_id)
    before_count = len(existing_rules)

    # Run thread analyzer on this specific PR
    analyzer_prompt = (
        f"Analyze PR #{pr_number} in repository '{repo}'. "
        f"Use github_fetch_comments with repo='{repo}', pr_number={pr_number}, github_token='{github_token}'. "
        f"Extract knowledge rules and store them using store_knowledge with repo_id={repo_id}."
    )
    await _run_agent("thread-analyzer", analyzer_prompt, repo_id)

    # Run synthesis against existing rules
    synth_prompt = (
        f"Synthesize all knowledge rules for repo_id={repo_id}. "
        f"Rules come from multiple sources: pr, structure, docs, ci_fix, config. "
        f"Apply cross-source prioritization, boost confidence for cross-source confirmations, "
        f"merge duplicates, and remove generic rules."
    )
    await _run_agent("synthesizer", synth_prompt, repo_id)

    # Check for new rules
    after_rules = await db.list_rules(repo_id=repo_id)
    new_rules = [r for r in after_rules if r["id"] > max((r2["id"] for r2 in existing_rules), default=0)]

    # Create proposals for new rules
    new_proposals = 0
    for rule in new_rules:
        await db.create_proposal(
            rule_text=rule["rule_text"],
            category=rule["category"],
            confidence=rule["confidence"],
            source_excerpt=f"Auto-extracted from merged PR #{pr_number}",
            proposed_by="webhook",
        )
        new_proposals += 1

    logger.info(f"Webhook extraction for PR #{pr_number}: {new_proposals} new proposals")
    return new_proposals


async def generate_claude_md(repo_id: int) -> str:
    """Generate CLAUDE.md content from the knowledge base for a given repo."""
    # First try generating via the AI agent
    try:
        generator_prompt = (
            f"Generate a CLAUDE.md file from all knowledge rules with repo_id={repo_id}. "
            f"Use list_all_knowledge to retrieve rules, then organize them into a well-structured "
            f"CLAUDE.md with sections: Quick Start, Development Commands, Code Style, Testing, "
            f"Architecture, Workflow, and Do Not. "
            f"Only include rules with confidence >= 0.6. "
            f"The 'Do Not' section should highlight CRITICAL prohibitions discovered from CI fixes and PR reviews."
        )
        result = await _run_agent("generator", generator_prompt, repo_id)
        if result.strip():
            return result
    except Exception as e:
        logger.warning(f"Agent-based CLAUDE.md generation failed: {e}")

    # Fallback: build CLAUDE.md directly from rules in the database
    rules = await db.list_rules(repo_id=repo_id)
    team_rules = await db.list_rules()
    seen_ids = {r["id"] for r in rules}
    for r in team_rules:
        if r["id"] not in seen_ids:
            rules.append(r)
    if not rules:
        return "# CLAUDE.md\n\nNo knowledge rules extracted yet. Run an extraction first.\n"

    # Map categories to the new three-tier structure
    section_map = {
        "workflow": "Workflow",
        "style": "Code Style",
        "testing": "Testing",
        "architecture": "Architecture",
        "security": "Security",
        "performance": "Performance",
        "general": "General",
    }

    lines = ["# CLAUDE.md\n"]

    # Separate prohibitions for the "Do Not" section
    do_not_rules = []
    regular_rules: dict[str, list[dict]] = {}

    for rule in rules:
        if rule["confidence"] < 0.6:
            continue
        text = rule["rule_text"]
        if any(kw in text.upper() for kw in ["NEVER", "DO NOT", "DON'T", "MUST NOT", "FORBIDDEN", "AVOID"]):
            do_not_rules.append(rule)
        else:
            section = section_map.get(rule["category"], "General")
            regular_rules.setdefault(section, []).append(rule)

    # Output regular sections
    section_order = ["Quick Start", "Development Commands", "Code Style", "Testing", "Architecture", "Workflow", "Security", "Performance", "General"]
    for section in section_order:
        cat_rules = regular_rules.get(section, [])
        if not cat_rules:
            continue
        lines.append(f"\n## {section}\n")
        for r in sorted(cat_rules, key=lambda x: -x["confidence"]):
            lines.append(f"- {r['rule_text']}")

    # Output Do Not section
    if do_not_rules:
        lines.append("\n## Do Not\n")
        for r in sorted(do_not_rules, key=lambda x: -x["confidence"]):
            lines.append(f"- {r['rule_text']}")

    return "\n".join(lines) + "\n"

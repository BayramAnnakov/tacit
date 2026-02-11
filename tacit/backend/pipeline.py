"""Extraction pipeline orchestrator using Claude Agent SDK."""

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from claude_agent_sdk import (
    query,
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
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    result_text.append(block.text)
        elif isinstance(message, ResultMessage):
            if message.is_error:
                logger.error(f"Agent {agent_name} error: {message.result}")

    return "\n".join(result_text)


async def run_extraction(repo: str, github_token: str) -> AsyncIterator[ExtractionEvent]:
    """Orchestrate the 4-pass extraction pipeline.

    Pass 1: PR Scanner - identify knowledge-rich PRs
    Pass 2: Thread Analyzer - extract rules from each PR
    Pass 3: Synthesizer - merge and deduplicate rules
    Pass 4: (optional) Generator can be called separately via /api/claude-md

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
        # --- Pass 1: Scan PRs ---
        yield ExtractionEvent(
            event_type="stage_change",
            stage="scanning",
            message=f"Scanning PRs in {repo} for knowledge-rich discussions...",
        )
        await db.update_extraction_run(run_id, stage="scanning")

        scanner_prompt = (
            f"Scan the GitHub repository '{repo}' for knowledge-rich pull requests. "
            f"Use the github_fetch_prs tool with github_token='{github_token}' and repo='{repo}'. "
            f"Return the top 10 most promising PRs as JSON."
        )
        scanner_result = await _run_agent("pr-scanner", scanner_prompt, repo_id)

        # Parse PR numbers from scanner output
        pr_numbers = []
        try:
            # Try to extract JSON from the result
            for line in scanner_result.split("\n"):
                line = line.strip()
                if line.startswith("["):
                    data = json.loads(line)
                    pr_numbers = [item["pr_number"] for item in data if "pr_number" in item]
                    break
            if not pr_numbers:
                # Fallback: try parsing the whole result as JSON
                data = json.loads(scanner_result)
                if isinstance(data, list):
                    pr_numbers = [item["pr_number"] for item in data if "pr_number" in item]
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not parse PR numbers from scanner output, using top 5 PRs")
            pr_numbers = list(range(1, 6))  # Fallback

        yield ExtractionEvent(
            event_type="progress",
            stage="scanning",
            message=f"Found {len(pr_numbers)} knowledge-rich PRs",
            data={"pr_count": len(pr_numbers)},
        )

        # --- Pass 2: Analyze each PR thread ---
        yield ExtractionEvent(
            event_type="stage_change",
            stage="analyzing",
            message="Analyzing PR discussion threads...",
        )
        await db.update_extraction_run(run_id, stage="analyzing")

        rules_found = 0
        for i, pr_num in enumerate(pr_numbers[:10]):  # Limit to 10 PRs
            yield ExtractionEvent(
                event_type="progress",
                stage="analyzing",
                message=f"Analyzing PR #{pr_num} ({i+1}/{len(pr_numbers[:10])})",
                data={"pr_number": pr_num, "progress": i + 1, "total": len(pr_numbers[:10])},
            )

            analyzer_prompt = (
                f"Analyze PR #{pr_num} in repository '{repo}'. "
                f"Use github_fetch_comments with repo='{repo}', pr_number={pr_num}, github_token='{github_token}'. "
                f"Extract knowledge rules and store them using store_knowledge with repo_id={repo_id}."
            )
            await _run_agent("thread-analyzer", analyzer_prompt, repo_id)

            # Count rules after each PR
            rules = await db.list_rules(repo_id=repo_id)
            new_count = len(rules)
            if new_count > rules_found:
                yield ExtractionEvent(
                    event_type="rule_found",
                    stage="analyzing",
                    message=f"Extracted {new_count - rules_found} new rules from PR #{pr_num}",
                    data={"new_rules": new_count - rules_found, "total_rules": new_count},
                )
                rules_found = new_count

            await db.update_extraction_run(run_id, prs_analyzed=i + 1, rules_found=rules_found)

        # --- Pass 3: Synthesize ---
        yield ExtractionEvent(
            event_type="stage_change",
            stage="synthesizing",
            message="Synthesizing and deduplicating rules...",
        )
        await db.update_extraction_run(run_id, stage="synthesizing")

        synth_prompt = (
            f"Synthesize all knowledge rules for repo_id={repo_id}. "
            f"Search for existing rules, merge duplicates, boost confidence for confirmed rules, "
            f"and resolve any contradictions."
        )
        synth_result = await _run_agent("synthesizer", synth_prompt, repo_id)

        final_rules = await db.list_rules(repo_id=repo_id)
        await db.update_extraction_run(
            run_id,
            status="completed",
            stage="complete",
            rules_found=len(final_rules),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        yield ExtractionEvent(
            event_type="complete",
            stage="complete",
            message=f"Extraction complete: {len(final_rules)} rules from {len(pr_numbers[:10])} PRs",
            data={"total_rules": len(final_rules), "prs_analyzed": len(pr_numbers[:10])},
        )

    except Exception as e:
        logger.exception(f"Extraction pipeline error: {e}")
        await db.update_extraction_run(run_id, status="failed", stage="error")
        yield ExtractionEvent(
            event_type="error",
            stage="error",
            message=f"Extraction failed: {str(e)}",
        )


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


async def generate_claude_md(repo_id: int) -> str:
    """Generate CLAUDE.md content from the knowledge base for a given repo."""
    # First try generating via the AI agent
    try:
        generator_prompt = (
            f"Generate a CLAUDE.md file from all knowledge rules with repo_id={repo_id}. "
            f"Use search_knowledge to retrieve rules, then organize them into a well-structured markdown file. "
            f"Only include rules with confidence >= 0.6."
        )
        result = await _run_agent("generator", generator_prompt, repo_id)
        if result.strip():
            return result
    except Exception as e:
        logger.warning(f"Agent-based CLAUDE.md generation failed: {e}")

    # Fallback: build CLAUDE.md directly from rules in the database
    # Include repo-specific rules AND team-wide rules (repo_id=None)
    rules = await db.list_rules(repo_id=repo_id)
    team_rules = await db.list_rules()
    seen_ids = {r["id"] for r in rules}
    for r in team_rules:
        if r["id"] not in seen_ids:
            rules.append(r)
    if not rules:
        return "# CLAUDE.md\n\nNo knowledge rules extracted yet. Run an extraction first.\n"

    lines = ["# CLAUDE.md\n", "Project conventions extracted by Tacit.\n"]
    by_category: dict[str, list[dict]] = {}
    for rule in rules:
        if rule["confidence"] < 0.6:
            continue
        by_category.setdefault(rule["category"], []).append(rule)

    for category, cat_rules in sorted(by_category.items()):
        lines.append(f"\n## {category.title()}\n")
        for r in sorted(cat_rules, key=lambda x: -x["confidence"]):
            lines.append(f"- {r['rule_text']}")

    return "\n".join(lines) + "\n"

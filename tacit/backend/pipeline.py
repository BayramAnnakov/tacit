"""Extraction pipeline orchestrator using Claude Agent SDK."""

import os
os.environ.pop("CLAUDECODE", None)  # Allow nested Claude SDK calls from within Claude Code

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


async def run_extraction(
    repo: str, github_token: str, run_id: int | None = None, *,
    exclude_ground_truth: bool = False, max_prs: int = 50,
) -> AsyncIterator[ExtractionEvent]:
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
    if run_id is None:
        run = await db.create_extraction_run(repo_id)
        run_id = int(run["id"])

    try:
        # === Phase 1: Launch parallel analyzers ===
        yield ExtractionEvent(
            event_type="stage_change",
            stage="repo_analysis",
            message=f"Analyzing repository structure, docs, CI patterns, and anti-patterns for {repo}...",
        )
        await db.update_extraction_run(run_id, stage="repo_analysis")

        # Launch structural, docs, CI, code, and anti-pattern analysis in parallel
        structural_task = asyncio.create_task(
            _run_structural_analysis(repo, github_token, repo_id)
        )
        docs_task = asyncio.create_task(
            _run_docs_analysis(repo, github_token, repo_id, exclude_ground_truth=exclude_ground_truth)
        )
        ci_fixes_task = asyncio.create_task(
            _run_ci_failure_mining(repo, github_token, repo_id)
        )
        code_analysis_task = asyncio.create_task(
            _run_code_analysis(repo, github_token, repo_id)
        )
        anti_pattern_task = asyncio.create_task(
            _run_anti_pattern_mining(repo, github_token, repo_id)
        )
        domain_task = asyncio.create_task(
            _run_domain_analysis(repo, github_token, repo_id)
        )

        yield ExtractionEvent(
            event_type="progress",
            stage="repo_analysis",
            message="Launched parallel analysis: repo structure, docs, CI failures, code analysis, anti-patterns, domain",
            data={"parallel_tasks": ["structural", "docs", "ci_fixes", "code_analysis", "anti_patterns", "domain"]},
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
            f"Use the github_fetch_prs tool with github_token='{github_token}', repo='{repo}', per_page=100. "
            f"Prioritize first-timer PRs and PRs with CHANGES_REQUESTED reviews. "
            f"Return the top {max_prs} most promising PRs as JSON."
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
        for pr_num in pr_numbers[:max_prs]:
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
            structural_task, docs_task, ci_fixes_task, code_analysis_task, anti_pattern_task, domain_task,
            return_exceptions=True,
        )

        # Report parallel task results
        task_names = ["Structural analysis", "Docs analysis", "CI failure mining", "Code analysis", "Anti-pattern mining", "Domain analysis"]
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


async def _run_docs_analysis(
    repo: str, github_token: str, repo_id: int, *, exclude_ground_truth: bool = False,
) -> str:
    """Run the docs analyzer agent."""
    if exclude_ground_truth:
        prompt = (
            f"Analyze the contributing documentation of repository '{repo}'. "
            f"Use github_fetch_docs with repo='{repo}', github_token='{github_token}', exclude_ground_truth=true. "
            f"IMPORTANT: Do NOT fetch or extract from CLAUDE.md or AGENTS.md files — only use CONTRIBUTING.md, README, and other docs. "
            f"Store each convention using store_knowledge with source_type='docs' and repo_id={repo_id}."
        )
    else:
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


async def _run_anti_pattern_mining(repo: str, github_token: str, repo_id: int) -> str:
    """Run the anti-pattern miner agent on CHANGES_REQUESTED PRs."""
    prompt = (
        f"Mine anti-patterns from CHANGES_REQUESTED PR reviews in repository '{repo}'. "
        f"Use github_fetch_rejected_patterns with repo='{repo}', github_token='{github_token}'. "
        f"Extract 'Do Not' rules from recurring reviewer complaints. "
        f"Include provenance_url (link to the PR) and provenance_summary (what went wrong) with each rule. "
        f"Store each rule using store_knowledge with source_type='anti_pattern' and repo_id={repo_id}."
    )
    return await _run_agent("anti-pattern-miner", prompt, repo_id)


async def _run_domain_analysis(repo: str, github_token: str, repo_id: int) -> str:
    """Run the domain analyzer agent to discover domain/product/design knowledge."""
    prompt = (
        f"Analyze the domain, product, and design knowledge in repository '{repo}'. "
        f"Use github_fetch_readme_full with repo='{repo}', github_token='{github_token}' to get the full README. "
        f"Use github_fetch_repo_structure with repo='{repo}', github_token='{github_token}' to discover the file tree. "
        f"Identify and read domain-relevant files (ADRs, architecture docs, OpenAPI specs, design docs, glossaries, schema files). "
        f"Use github_fetch_file_content with repo='{repo}', github_token='{github_token}' to read each identified file. "
        f"Extract domain, design, and product knowledge rules using store_knowledge with repo_id={repo_id}."
    )
    return await _run_agent("domain-analyzer", prompt, repo_id)


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


async def mine_session(transcript_path: str, cwd: str = "") -> dict:
    """Mine a single Claude Code session transcript for tacit knowledge.

    Reads the JSONL transcript, extracts user/assistant messages,
    sends to the session-analyzer agent, and stores extracted rules.
    Returns session metadata with rules_found count.
    """
    from pathlib import Path
    path = Path(transcript_path)
    if not path.exists():
        logger.warning(f"Transcript not found: {transcript_path}")
        return {"path": transcript_path, "rules_found": 0, "error": "file not found"}

    # Check if already mined
    existing = await db.get_mined_session(transcript_path)
    if existing:
        return {"path": transcript_path, "rules_found": existing["rules_found"], "skipped": True}

    # Read JSONL transcript
    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    role = entry.get("role", "")
                    if role in ("user", "assistant"):
                        content = entry.get("content", "")
                        if isinstance(content, list):
                            # Extract text blocks from content array
                            text_parts = []
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                                elif isinstance(block, str):
                                    text_parts.append(block)
                            content = "\n".join(text_parts)
                        if content:
                            messages.append({"role": role, "content": str(content)[:1000]})
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Error reading transcript {transcript_path}: {e}")
        return {"path": transcript_path, "rules_found": 0, "error": str(e)}

    if len(messages) < 4:
        # Too short to extract meaningful knowledge
        await db.upsert_mined_session(transcript_path, cwd, len(messages), 0)
        return {"path": transcript_path, "message_count": len(messages), "rules_found": 0}

    # Build conversation summary for the agent (limit to ~30k chars)
    conversation_text = []
    char_budget = 30000
    for msg in messages:
        line = f"[{msg['role']}]: {msg['content']}"
        if sum(len(l) for l in conversation_text) + len(line) > char_budget:
            break
        conversation_text.append(line)

    prompt = (
        f"Analyze this Claude Code conversation transcript and extract tacit knowledge rules.\n"
        f"Project directory: {cwd or 'unknown'}\n\n"
        f"CONVERSATION:\n{''.join(chr(10) + l for l in conversation_text)}\n\n"
        f"Return a JSON array of extracted rules. Each rule needs: rule_text, category, confidence, source_excerpt."
    )

    try:
        result = await _run_agent("session-analyzer", prompt)

        # Parse rules from agent output
        rules_found = 0
        try:
            import re
            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                for rule_data in parsed:
                    if not isinstance(rule_data, dict) or not rule_data.get("rule_text"):
                        continue
                    await db.insert_rule(
                        rule_text=rule_data["rule_text"],
                        category=rule_data.get("category", "general"),
                        confidence=rule_data.get("confidence", 0.7),
                        source_type="conversation",
                        source_ref=f"session:{transcript_path}",
                    )
                    rules_found += 1
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Could not parse session analyzer output: {e}")

        await db.upsert_mined_session(transcript_path, cwd, len(messages), rules_found)
        return {"path": transcript_path, "message_count": len(messages), "rules_found": rules_found}

    except Exception as e:
        logger.error(f"Session analysis failed for {transcript_path}: {e}")
        await db.upsert_mined_session(transcript_path, cwd, len(messages), 0)
        return {"path": transcript_path, "message_count": len(messages), "rules_found": 0, "error": str(e)}


async def mine_all_sessions() -> list[dict]:
    """Scan all Claude Code project directories and mine transcripts.

    Scans ~/.claude/projects/ for JSONL transcripts, processes newest first,
    skips already-mined files.
    """
    from pathlib import Path
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return []

    # Collect all JSONL files with their modification times
    transcripts = []
    for proj_dir in claude_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        project_path = proj_dir.name  # encoded project path
        for jsonl_file in proj_dir.glob("*.jsonl"):
            transcripts.append({
                "path": str(jsonl_file),
                "project_path": project_path,
                "mtime": jsonl_file.stat().st_mtime,
            })

    # Sort newest first
    transcripts.sort(key=lambda t: t["mtime"], reverse=True)

    results = []
    for t in transcripts:
        result = await mine_session(t["path"], t["project_path"])
        results.append(result)

    return results


async def generate_claude_md(repo_id: int, *, fast: bool = False) -> str:
    """Generate CLAUDE.md content from the knowledge base for a given repo.

    If fast=True, skip the AI agent and build directly from DB rules.
    """
    if fast:
        # Jump straight to the fast fallback path (no LLM call)
        return await _build_claude_md_from_rules(repo_id)

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

    # Fallback to fast path
    return await _build_claude_md_from_rules(repo_id)


async def _build_claude_md_from_rules(repo_id: int) -> str:
    """Build CLAUDE.md directly from rules in the database (no LLM call)."""
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
        "domain": "Product Context",
        "design": "Design Conventions",
        "product": "Product Context",
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
    section_order = ["Quick Start", "Development Commands", "Code Style", "Testing", "Architecture", "Product Context", "Design Conventions", "Workflow", "Security", "Performance", "General"]
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


async def incremental_extract(repo: str, pr_number: int, github_token: str) -> dict:
    """Extract knowledge from a single merged PR incrementally.

    Unlike run_single_pr_extraction, this:
    1. Also runs anti-pattern mining on the specific PR
    2. Performs lightweight dedup synthesis (not full re-synthesis)
    3. Auto-approves high-confidence rules (>= 0.85)
    4. Creates proposals for lower-confidence rules
    Returns summary of actions taken.
    """
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == repo:
            repo_record = r
            break

    if not repo_record:
        logger.warning(f"Repo {repo} not found for incremental extraction")
        return {"new_rules": 0, "new_proposals": 0, "error": "repo not found"}

    repo_id = repo_record["id"]

    # Get existing rule IDs before extraction
    existing_rules = await db.list_rules(repo_id=repo_id)
    existing_ids = {r["id"] for r in existing_rules}

    # Run thread analyzer on this specific PR
    analyzer_prompt = (
        f"Analyze PR #{pr_number} in repository '{repo}'. "
        f"Use github_fetch_comments with repo='{repo}', pr_number={pr_number}, github_token='{github_token}'. "
        f"Extract knowledge rules and store them using store_knowledge with repo_id={repo_id}. "
        f"Include provenance_url='https://github.com/{repo}/pull/{pr_number}' and "
        f"provenance_summary describing the context from the PR discussion. "
        f"Also include applicable_paths if the rule is specific to certain directories."
    )
    await _run_agent("thread-analyzer", analyzer_prompt, repo_id)

    # Get new rules
    all_rules = await db.list_rules(repo_id=repo_id)
    new_rules = [r for r in all_rules if r["id"] not in existing_ids]

    # Lightweight dedup: check each new rule against existing rules
    auto_approved = 0
    proposals_created = 0

    for new_rule in new_rules:
        # Check for duplicates via text similarity
        is_dup = False
        for existing in existing_rules:
            from difflib import SequenceMatcher
            sim = SequenceMatcher(None, new_rule["rule_text"].lower(), existing["rule_text"].lower()).ratio()
            if sim > 0.7:
                # Duplicate — delete the new one, optionally boost existing
                await db.delete_rule(new_rule["id"])
                is_dup = True
                break

        if is_dup:
            continue

        # Auto-approve high-confidence rules, create proposals for others
        if new_rule["confidence"] >= 0.85:
            auto_approved += 1
            await db.add_trail_entry(
                rule_id=new_rule["id"],
                event_type="auto_approved",
                description=f"Auto-approved from incremental extraction of PR #{pr_number} (confidence {new_rule['confidence']:.2f})",
                source_ref=f"pr:{repo}#{pr_number}",
            )
        else:
            await db.create_proposal(
                rule_text=new_rule["rule_text"],
                category=new_rule["category"],
                confidence=new_rule["confidence"],
                source_excerpt=f"Incrementally extracted from merged PR #{pr_number}",
                proposed_by="webhook",
            )
            # Remove from rules (it's a proposal now, not approved yet)
            await db.delete_rule(new_rule["id"])
            proposals_created += 1

    logger.info(
        f"Incremental extraction for PR #{pr_number}: "
        f"{auto_approved} auto-approved, {proposals_created} proposals"
    )
    return {
        "pr_number": pr_number,
        "new_rules": auto_approved,
        "new_proposals": proposals_created,
        "total_extracted": len(new_rules),
    }


async def collect_outcome_metrics(repo: str, github_token: str, repo_id: int, days: int = 14) -> dict:
    """Collect outcome metrics for a repository via the outcome-analyzer agent."""
    prompt = (
        f"Collect outcome metrics for repository '{repo}'. "
        f"Use github_fetch_outcome_metrics with repo='{repo}', github_token='{github_token}', days={days}. "
        f"Then use list_all_knowledge with repo_id={repo_id} to count deployed rules. "
        f"Return a JSON object with the metrics."
    )

    result = await _run_agent("outcome-analyzer", prompt, repo_id)

    # Parse metrics from agent output
    try:
        import re
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Could not parse outcome metrics: {e}")

    return {}


async def generate_modular_rules(repo_id: int, *, fast: bool = False) -> dict:
    """Generate a .claude/rules/ directory structure from the knowledge base.

    Returns a dict mapping file paths to content strings.
    If fast=True, skip the AI agent and build directly from DB rules.
    """
    if fast:
        return await _build_modular_rules_fallback(repo_id)

    # First try via AI agent
    try:
        prompt = (
            f"Generate a modular .claude/rules/ directory structure from all knowledge rules with repo_id={repo_id}. "
            f"Use list_all_knowledge to retrieve rules, then organize them into path-scoped rule files. "
            f"Rules with applicable_paths should get YAML frontmatter with paths: field. "
            f"Anti-pattern/Do Not rules go in do-not.md (always loaded). "
            f"Return a JSON object mapping file paths to content strings."
        )
        result = await _run_agent("modular-generator", prompt, repo_id)

        import re
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.warning(f"Agent-based modular generation failed: {e}")

    # Fallback: build directly from rules
    return await _build_modular_rules_fallback(repo_id)


async def _build_modular_rules_fallback(repo_id: int) -> dict:
    """Build modular rules directly from DB when agent fails."""
    rules = await db.list_rules(repo_id=repo_id)
    if not rules:
        return {".claude/CLAUDE.md": "# CLAUDE.md\n\nNo rules extracted yet.\n"}

    # Categorize rules
    files: dict[str, list[str]] = {}
    do_not_rules: list[str] = []

    category_to_file = {
        "workflow": ".claude/rules/workflow.md",
        "style": ".claude/rules/code-style.md",
        "testing": ".claude/rules/testing.md",
        "architecture": ".claude/rules/architecture.md",
        "security": ".claude/rules/security.md",
        "performance": ".claude/rules/performance.md",
        "domain": ".claude/rules/domain.md",
        "design": ".claude/rules/design.md",
        "product": ".claude/rules/product.md",
        "general": ".claude/rules/general.md",
    }

    for rule in rules:
        if rule["confidence"] < 0.6:
            continue

        text = rule["rule_text"]
        paths = rule.get("applicable_paths", "")

        # Check if it's a "Do Not" rule
        if any(kw in text.upper() for kw in ["NEVER", "DO NOT", "DON'T", "MUST NOT", "FORBIDDEN", "AVOID"]):
            provenance = ""
            if rule.get("provenance_summary"):
                provenance = f" ({rule['provenance_summary'][:100]})"
            do_not_rules.append(f"- {text}{provenance}")
            continue

        # Path-scoped rules go to subdirectory files
        if paths:
            path_parts = paths.split(",")[0].strip().split("/")
            if len(path_parts) >= 2:
                subdir = path_parts[0] if path_parts[0] not in ("src", "lib") else path_parts[1]
                file_key = f".claude/rules/{subdir}/{rule['category']}.md"
            else:
                file_key = category_to_file.get(rule["category"], ".claude/rules/general.md")
        else:
            file_key = category_to_file.get(rule["category"], ".claude/rules/general.md")

        files.setdefault(file_key, []).append(f"- {text}")

    result: dict[str, str] = {}

    # Core CLAUDE.md
    result[".claude/CLAUDE.md"] = "# CLAUDE.md\n\nSee `.claude/rules/` for detailed conventions.\n"

    # Do Not file (always loaded)
    if do_not_rules:
        result[".claude/rules/do-not.md"] = (
            "---\ndescription: Critical anti-patterns — things that WILL cause problems if ignored\n---\n\n"
            + "\n".join(do_not_rules) + "\n"
        )

    # Category files
    for file_path, rule_lines in sorted(files.items()):
        category = file_path.split("/")[-1].replace(".md", "").replace("-", " ").title()
        # Check if any rules in this file have path scoping
        content = f"---\ndescription: {category} conventions\n---\n\n"
        content += "\n".join(rule_lines) + "\n"
        result[file_path] = content

    return result

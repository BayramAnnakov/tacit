"""Agent definitions using Claude Agent SDK AgentDefinition."""

from pathlib import Path

from claude_agent_sdk import AgentDefinition

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt file from the prompts directory."""
    return (PROMPTS_DIR / filename).read_text()


def get_agent_definitions() -> dict[str, AgentDefinition]:
    """Return all agent definitions for the extraction pipeline."""
    return {
        "pr-scanner": AgentDefinition(
            description="Scans PR metadata to identify knowledge-rich discussions worth analyzing",
            prompt=_load_prompt("pr_scanner.md"),
            model="sonnet",
            tools=["github_fetch_prs"],
        ),
        "thread-analyzer": AgentDefinition(
            description="Deep-analyzes PR discussion threads to extract specific knowledge rules",
            prompt=_load_prompt("thread_analyzer.md"),
            model="opus",
            tools=["github_fetch_comments", "search_knowledge", "store_knowledge"],
        ),
        "structural-analyzer": AgentDefinition(
            description="Extracts conventions from repo tree, commit messages, and branch policies",
            prompt=_load_prompt("structural_analyzer.md"),
            model="sonnet",
            tools=["github_fetch_repo_structure", "store_knowledge", "search_knowledge"],
        ),
        "docs-analyzer": AgentDefinition(
            description="Extracts conventions from CONTRIBUTING.md, README, and existing CLAUDE.md",
            prompt=_load_prompt("docs_analyzer.md"),
            model="sonnet",
            tools=["github_fetch_docs", "store_knowledge", "search_knowledge"],
        ),
        "ci-failure-miner": AgentDefinition(
            description="Mines CI failure-to-fix patterns to discover implicit conventions",
            prompt=_load_prompt("ci_failure_miner.md"),
            model="opus",
            tools=["github_fetch_ci_fixes", "store_knowledge", "search_knowledge"],
        ),
        "synthesizer": AgentDefinition(
            description="Cross-source synthesis: merges, deduplicates, boosts, and refines extracted rules",
            prompt=_load_prompt("synthesizer.md"),
            model="opus",
            tools=["list_all_knowledge", "search_knowledge", "store_knowledge", "delete_knowledge"],
        ),
        "generator": AgentDefinition(
            description="Generates a well-structured CLAUDE.md file from the knowledge base",
            prompt=_load_prompt("generator.md"),
            model="opus",
            tools=["list_all_knowledge", "search_knowledge"],
        ),
        "local-extractor": AgentDefinition(
            description="Extracts knowledge from local Claude Code conversation logs",
            prompt=_load_prompt("local_extractor.md"),
            model="sonnet",
            tools=["read_claude_logs", "store_knowledge", "search_knowledge"],
        ),
    }

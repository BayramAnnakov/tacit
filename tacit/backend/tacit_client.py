#!/usr/bin/env python3
"""Standalone CLI client for federated contribution to a Tacit server.

Extracts knowledge rules from local Claude Code conversation logs and
submits them to a Tacit server as proposals.

Usage:
    python tacit_client.py /path/to/project --server http://tacit:8000 --name "Bayram"
    python tacit_client.py /path/to/project --dry-run
    python tacit_client.py /path/to/project --no-agent  # lightweight heuristic mode (default)
"""

import argparse
import getpass
import json
import re
import subprocess
import sys
from pathlib import Path

CLIENT_VERSION = "0.1.0"

# Heuristic patterns that indicate a knowledge rule in assistant messages.
# Each tuple is (compiled regex, category guess, base confidence).
_HEURISTIC_PATTERNS = [
    (re.compile(r"\bAlways\b\s+", re.IGNORECASE), "workflow", 0.70),
    (re.compile(r"\bNever\b\s+", re.IGNORECASE), "workflow", 0.75),
    (re.compile(r"\bDon'?t\b\s+", re.IGNORECASE), "style", 0.65),
    (re.compile(r"\bUse\s+\S+\s+instead\s+of\s+", re.IGNORECASE), "style", 0.75),
    (re.compile(r"\bPrefer\s+\S+\s+over\s+", re.IGNORECASE), "style", 0.70),
    (re.compile(r"\bEnsure\b\s+", re.IGNORECASE), "workflow", 0.65),
    (re.compile(r"\bMake\s+sure\s+to\b\s+", re.IGNORECASE), "workflow", 0.65),
    (re.compile(r"\bAvoid\b\s+", re.IGNORECASE), "style", 0.70),
    (re.compile(r"\bMust\b\s+", re.IGNORECASE), "architecture", 0.70),
    (re.compile(r"\bShould\s+always\b\s+", re.IGNORECASE), "workflow", 0.65),
    (re.compile(r"\bImportant:\s+", re.IGNORECASE), "general", 0.60),
]

# Maximum length for a single extracted rule sentence.
_MAX_RULE_LEN = 300
_MIN_RULE_LEN = 20


# --------------- Path encoding (matches server's read_claude_logs) ---------------

def encode_project_path(project_path: str) -> str:
    """Encode a project path the same way Claude Code does: replace / with - and strip leading -."""
    return project_path.replace("/", "-").lstrip("-")


def find_log_dir(project_path: str) -> Path | None:
    """Find the Claude Code log directory for a project path."""
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    encoded = encode_project_path(project_path)
    matches = list(claude_dir.glob(f"*{encoded}*"))
    if matches:
        return matches[0]

    # Fallback: try exact match
    exact = claude_dir / encoded
    if exact.exists():
        return exact

    return None


# --------------- Log reading ---------------

def read_assistant_messages(log_dir: Path, limit: int = 100) -> list[str]:
    """Read assistant message texts from JSONL files in the log directory."""
    messages: list[str] = []
    jsonl_files = sorted(log_dir.glob("*.jsonl"), reverse=True)

    for jsonl_file in jsonl_files:
        with open(jsonl_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Claude Code JSONL format: top-level "type" field indicates
                # the message type, and content is nested under "message".
                if entry.get("type") != "assistant":
                    continue

                # Content is at entry["message"]["content"] — a list of blocks
                message = entry.get("message", {})
                if not isinstance(message, dict):
                    continue
                raw_content = message.get("content", "")

                content = ""
                if isinstance(raw_content, list):
                    text_parts = []
                    for block in raw_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = "\n".join(text_parts)
                elif isinstance(raw_content, str):
                    content = raw_content

                if content:
                    messages.append(content)

                if len(messages) >= limit:
                    break
        if len(messages) >= limit:
            break

    return messages


# --------------- Heuristic extraction (no-agent mode) ---------------

def extract_rules_heuristic(messages: list[str]) -> list[dict]:
    """Extract knowledge rules from assistant messages using pattern matching."""
    rules: list[dict] = []
    seen_texts: set[str] = set()

    for message in messages:
        # Split into sentences (approximate)
        sentences = re.split(r'(?<=[.!])\s+', message)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < _MIN_RULE_LEN or len(sentence) > _MAX_RULE_LEN:
                continue

            for pattern, category, confidence in _HEURISTIC_PATTERNS:
                if pattern.search(sentence):
                    # Normalize for dedup
                    normalized = sentence.lower().strip()
                    if normalized in seen_texts:
                        break
                    seen_texts.add(normalized)

                    rules.append({
                        "rule_text": sentence,
                        "category": category,
                        "confidence": confidence,
                        "source_excerpt": sentence[:200],
                    })
                    break  # One match per sentence is enough

    return rules


# --------------- Agent extraction ---------------

def extract_rules_agent(messages: list[str]) -> list[dict]:
    """Extract knowledge rules using ClaudeSDKClient with a capture MCP server."""
    try:
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, tool, create_sdk_mcp_server
    except ImportError:
        print("Error: claude_agent_sdk is required for agent mode.", file=sys.stderr)
        print("Install it or use --no-agent for lightweight extraction.", file=sys.stderr)
        sys.exit(1)

    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required for agent mode.", file=sys.stderr)
        sys.exit(1)

    # In-memory capture list
    captured_rules: list[dict] = []

    @tool(
        name="store_knowledge",
        description="Store an extracted knowledge rule. Call this for each convention you identify.",
        input_schema={
            "type": "object",
            "properties": {
                "rule_text": {"type": "string", "description": "The knowledge rule text"},
                "category": {"type": "string", "description": "Category: architecture, testing, style, workflow, security, performance, general"},
                "confidence": {"type": "number", "description": "Confidence score 0.0-1.0"},
                "source_excerpt": {"type": "string", "description": "Excerpt from conversation that supports this rule"},
            },
            "required": ["rule_text", "category", "confidence"],
        },
    )
    async def capture_store_knowledge(args: dict) -> dict:
        captured_rules.append({
            "rule_text": args["rule_text"],
            "category": args.get("category", "general"),
            "confidence": args.get("confidence", 0.7),
            "source_excerpt": args.get("source_excerpt", ""),
        })
        return {"content": [{"type": "text", "text": f"Stored rule: {args['rule_text'][:80]}..."}]}

    server = create_sdk_mcp_server(
        name="tacit_client_capture",
        version=CLIENT_VERSION,
        tools=[capture_store_knowledge],
    )

    # Prepare conversation text (truncated to fit context)
    conversation_text = "\n---\n".join(messages[:50])
    if len(conversation_text) > 30000:
        conversation_text = conversation_text[:30000] + "\n[...truncated]"

    prompt = (
        "Analyze the following Claude Code conversation excerpts and extract team knowledge rules. "
        "For each convention, best practice, or important pattern you find, call store_knowledge. "
        "Focus on actionable, project-specific rules. Skip generic programming advice.\n\n"
        f"Conversation excerpts:\n\n{conversation_text}"
    )

    client = ClaudeSDKClient()
    options = ClaudeAgentOptions(
        model="sonnet",
        mcp_servers=[server],
        allowed_tools=[f"mcp__tacit_client_capture__store_knowledge"],
        max_turns=10,
    )

    import asyncio
    asyncio.run(client.run(prompt, options))

    return captured_rules


# --------------- Git remote detection ---------------

def detect_project_hint(project_path: str) -> str:
    """Auto-detect owner/repo from git remote origin URL."""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return ""

        url = result.stdout.strip()
        # Normalize: git@github.com:owner/repo.git -> owner/repo
        # https://github.com/owner/repo.git -> owner/repo
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        if "github.com:" in url:
            # SSH format: git@github.com:owner/repo
            return url.split("github.com:")[-1]
        elif "github.com/" in url:
            # HTTPS format: https://github.com/owner/repo
            parts = url.split("github.com/")[-1]
            segments = parts.split("/")
            if len(segments) >= 2:
                return f"{segments[0]}/{segments[1]}"

        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


# --------------- Submission ---------------

def submit_contribution(
    server_url: str,
    contributor_name: str,
    rules: list[dict],
    project_hint: str,
) -> dict:
    """Submit extracted rules to the Tacit server via POST /api/contribute."""
    import httpx

    payload = {
        "contributor_name": contributor_name,
        "rules": rules,
        "project_hint": project_hint,
        "client_version": CLIENT_VERSION,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{server_url.rstrip('/')}/api/contribute", json=payload)
        resp.raise_for_status()
        return resp.json()


# --------------- CLI ---------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tacit Client: extract knowledge from Claude Code logs and contribute to a Tacit server.",
    )
    parser.add_argument("project_path", help="Path to the project directory")
    parser.add_argument("--server", default="http://localhost:8000", help="Tacit server URL (default: http://localhost:8000)")
    parser.add_argument("--name", default=getpass.getuser(), help="Contributor name (default: OS username)")
    parser.add_argument("--no-agent", action="store_true", default=True, help="Use lightweight heuristic extraction (default)")
    parser.add_argument("--agent", action="store_true", help="Use agent-based extraction (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--dry-run", action="store_true", help="Extract and print rules without submitting")
    parser.add_argument("--limit", type=int, default=100, help="Max JSONL entries to scan (default: 100)")

    args = parser.parse_args()

    project_path = str(Path(args.project_path).resolve())
    use_agent = args.agent  # --agent overrides --no-agent

    # Find log directory
    log_dir = find_log_dir(project_path)
    if not log_dir:
        print(f"No Claude Code logs found for: {project_path}", file=sys.stderr)
        print(f"Expected logs in: ~/.claude/projects/{encode_project_path(project_path)}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading logs from: {log_dir}")

    # Read assistant messages
    messages = read_assistant_messages(log_dir, limit=args.limit)
    if not messages:
        print("No assistant messages found in logs.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(messages)} assistant messages")

    # Extract rules
    if use_agent:
        print("Extracting rules with agent mode...")
        rules = extract_rules_agent(messages)
    else:
        print("Extracting rules with heuristic mode...")
        rules = extract_rules_heuristic(messages)

    if not rules:
        print("No rules extracted.")
        sys.exit(0)

    print(f"\nExtracted {len(rules)} rule(s):\n")

    # Detect project hint
    project_hint = detect_project_hint(project_path)
    if project_hint:
        print(f"Detected project: {project_hint}")

    # Display rules
    for i, rule in enumerate(rules, 1):
        print(f"  [{i}] ({rule['category']}, conf={rule['confidence']:.2f}) {rule['rule_text']}")

    # Dry-run or submit
    if args.dry_run:
        print(f"\n--dry-run: {len(rules)} rule(s) not submitted.")
        return

    print(f"\nSubmitting {len(rules)} rule(s) to {args.server}...")
    try:
        response = submit_contribution(args.server, args.name, rules, project_hint)
    except Exception as e:
        print(f"Submission failed: {e}", file=sys.stderr)
        sys.exit(1)

    accepted = response.get("accepted", 0)
    print(f"\nServer accepted {accepted} rule(s):")
    for result in response.get("results", []):
        action = result.get("action", "?")
        pid = result.get("proposal_id", "?")
        count = result.get("contributor_count", 1)
        print(f"  - Proposal #{pid}: {action} (contributors: {count})")

    print("\nDone.")


if __name__ == "__main__":
    main()

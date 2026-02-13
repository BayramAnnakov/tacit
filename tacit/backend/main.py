"""FastAPI application with REST endpoints and WebSocket for Tacit."""

import asyncio
import difflib
import json
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
import proposals as prop
from pipeline import (
    run_extraction, run_local_extraction, generate_claude_md,
    run_single_pr_extraction, mine_session, mine_all_sessions,
    incremental_extract, collect_outcome_metrics, generate_modular_rules,
)
from config import settings
from models import ExtractionEvent, PRValidationRequest, RuleViolation, PRValidationResult


# --------------- Semantic Similarity ---------------

async def find_semantic_match(
    rule_text: str,
    pending_proposals: list[dict],
) -> tuple[dict | None, float]:
    """Use Claude to find the best semantic match for a rule among pending proposals.

    Returns (matching_proposal, similarity_score) or (None, 0.0) if no match.
    Falls back to SequenceMatcher if ANTHROPIC_API_KEY is missing or Claude call fails.
    """
    if not pending_proposals:
        return None, 0.0

    # Fallback: use SequenceMatcher if no API key
    if not settings.ANTHROPIC_API_KEY:
        return _sequencematcher_fallback(rule_text, pending_proposals)

    try:
        return await asyncio.wait_for(
            _claude_semantic_match(rule_text, pending_proposals),
            timeout=10.0,
        )
    except Exception as e:
        logger.warning(f"Claude semantic match failed, falling back to SequenceMatcher: {e}")
        return _sequencematcher_fallback(rule_text, pending_proposals)


def _sequencematcher_fallback(
    rule_text: str,
    pending_proposals: list[dict],
) -> tuple[dict | None, float]:
    """Character-level similarity fallback using SequenceMatcher."""
    best_match = None
    best_score = 0.0
    for proposal in pending_proposals:
        score = SequenceMatcher(
            None, rule_text.lower(), proposal["rule_text"].lower()
        ).ratio()
        if score > 0.65 and score > best_score:
            best_match = proposal
            best_score = score
    return best_match, best_score


async def _claude_semantic_match(
    rule_text: str,
    pending_proposals: list[dict],
) -> tuple[dict | None, float]:
    """Call Claude to semantically compare a rule against pending proposals."""
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock

    # Build numbered list of proposals
    proposals_text = "\n".join(
        f"{i}: {p['rule_text']}" for i, p in enumerate(pending_proposals)
    )

    system_prompt = (
        "You compare software development rules for semantic similarity. "
        "Respond with ONLY a JSON object, no other text. "
        "Format: {\"match_index\": N, \"similarity\": 0.XX} "
        "where match_index is the 0-based index of the best match (-1 if none are similar) "
        "and similarity is a float from 0.0 to 1.0. "
        "Two rules are similar if they express the same convention or practice, "
        "even if worded differently."
    )

    user_prompt = (
        f"New rule: \"{rule_text}\"\n\n"
        f"Existing proposals:\n{proposals_text}\n\n"
        "Which existing proposal (if any) is semantically the same as the new rule? "
        "Return JSON with match_index and similarity."
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model="sonnet",
        mcp_servers={},
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=1,
    )

    result_text = []
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        await client.query(user_prompt)
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                if message.is_error:
                    logger.error(f"Claude semantic match error: {message.result}")
                    return None, 0.0
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text.append(block.text)
    finally:
        await client.disconnect()

    # Parse JSON response
    raw = "".join(result_text).strip()
    # Extract JSON from potential markdown code blocks
    if "```" in raw:
        import re
        json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)

    parsed = json.loads(raw)
    match_index = parsed.get("match_index", -1)
    similarity = float(parsed.get("similarity", 0.0))

    if match_index >= 0 and match_index < len(pending_proposals) and similarity >= 0.60:
        return pending_proposals[match_index], similarity

    return None, 0.0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------- Seed Data ---------------

async def seed_demo_data() -> None:
    """Seed the database with demo team members, proposals, rules, and decision trails."""
    # Team members
    await db.create_team_member("Bayram", "🎯", "team lead")
    await db.create_team_member("Alex", "⚡", "frontend dev")
    await db.create_team_member("Sarah", "🔧", "backend dev")

    # Check if we already have proposals (avoid duplicates on restart)
    existing = await db.list_proposals()
    if len(existing) > 0:
        return

    # Create sample repository
    repo = await db.create_repo("anthropics", "claude-code")
    repo_id = repo["id"]

    # --- Sample Knowledge Rules (pre-seeded for demo) ---
    rules_data = [
        ("Only use Anthropic's own API providers (direct Anthropic API, AWS Bedrock, Google Vertex). Third-party proxies are unsupported.",
         "architecture", 0.95, "pr", "anthropics/claude-code#1247", repo_id),
        ("Test subprocess interactions against non-POSIX shells (fish, nushell, zsh) in addition to bash.",
         "testing", 0.90, "pr", "anthropics/claude-code#892", repo_id),
        ("Extract distinct responsibilities from large service classes into separate utility classes.",
         "architecture", 0.85, "pr", "anthropics/claude-code#1103", repo_id),
        ("Use mock gateways in integration tests to prevent real HTTP calls.",
         "testing", 0.80, "pr", "anthropics/claude-code#967", repo_id),
        ("Replace complex conditional logic with rule-based decision maps using clear priority ordering.",
         "style", 0.85, "pr", "anthropics/claude-code#1054", repo_id),
        ("Do not require elevated permissions for terminal UI features to render correctly.",
         "architecture", 0.75, "pr", "anthropics/claude-code#1301", repo_id),
        ("Auto-lock closed issues after 7 days of inactivity.",
         "workflow", 0.95, "pr", "anthropics/claude-code#788", repo_id),
        ("Document security vulnerability reporting in a SECURITY.md file at the repository root.",
         "security", 0.85, "pr", "anthropics/claude-code#1156", repo_id),
    ]

    for rule_text, category, confidence, source_type, source_ref, rid in rules_data:
        rule = await db.insert_rule(rule_text, category, confidence, source_type, source_ref, rid)
        await db.add_trail_entry(
            rule_id=rule["id"],
            event_type="created",
            description=f"Extracted from {source_ref}",
            source_ref=source_ref,
        )

    # Add a second trail entry on some rules (to show evolution)
    first_rule = await db.get_rule(1)
    if first_rule:
        await db.add_trail_entry(
            rule_id=1,
            event_type="confidence_boost",
            description="Confirmed by 3 additional PRs discussing API provider compatibility",
            source_ref="anthropics/claude-code#1302,#1315,#1340",
        )

    # --- Sample Proposals ---
    await db.create_proposal(
        rule_text="Use @MainActor for all SwiftUI view models to ensure UI updates happen on the main thread",
        category="architecture",
        confidence=0.85,
        source_excerpt="Alex: 'We keep getting threading crashes when view models update from background tasks. Let's enforce @MainActor on all VMs.'",
        proposed_by="Alex",
    )
    await db.create_proposal(
        rule_text="Prefer async/await over Combine publishers for new network calls",
        category="style",
        confidence=0.78,
        source_excerpt="Alex: 'The team agreed in PR #42 that async/await is more readable than Combine chains for simple network requests.'",
        proposed_by="Alex",
    )
    await db.create_proposal(
        rule_text="All API endpoints must return structured error responses with error_code and message fields",
        category="architecture",
        confidence=0.92,
        source_excerpt="Sarah: 'Inconsistent error formats caused 3 frontend bugs last sprint. Standardizing on {error_code, message} format.'",
        proposed_by="Sarah",
    )

    # --- Federated contribution demo data ---
    # Create a proposal with multiple contributors (consensus)
    fed_proposal = await db.create_proposal(
        rule_text="Use structured logging (JSON format) instead of print statements for all backend services",
        category="architecture",
        confidence=0.92,
        source_excerpt="Multiple team members independently identified this pattern from debugging sessions",
        proposed_by="Sarah",
    )
    fed_id = fed_proposal["id"]
    await db.add_proposal_contribution(
        proposal_id=fed_id, contributor_name="Sarah",
        original_rule_text="Use structured logging (JSON format) instead of print statements for all backend services",
        original_confidence=0.85, source_excerpt="From debugging a production incident", similarity_score=1.0,
    )
    await db.add_proposal_contribution(
        proposal_id=fed_id, contributor_name="Alex",
        original_rule_text="Always use JSON-formatted logging instead of print() for server-side code",
        original_confidence=0.80, source_excerpt="Claude suggested this pattern in code review", similarity_score=0.72,
    )
    await db.add_proposal_contribution(
        proposal_id=fed_id, contributor_name="Bayram",
        original_rule_text="Replace print debugging with structured JSON logs for better observability",
        original_confidence=0.88, source_excerpt="Noticed during log aggregation setup", similarity_score=0.68,
    )
    await db.update_proposal_confidence(fed_id, consensus_confidence(0.85, 3), 3)
    if repo_id:
        await db.update_proposal_repo_id(fed_id, repo_id)

    fed_proposal2 = await db.create_proposal(
        rule_text="Pin all Python dependencies to exact versions in requirements.txt",
        category="workflow",
        confidence=0.88,
        source_excerpt="Two developers hit dependency conflicts in the same week",
        proposed_by="Alex",
    )
    fed2_id = fed_proposal2["id"]
    await db.add_proposal_contribution(
        proposal_id=fed2_id, contributor_name="Alex",
        original_rule_text="Pin all Python dependencies to exact versions in requirements.txt",
        original_confidence=0.82, source_excerpt="Hit a breaking change from an unpinned dep", similarity_score=1.0,
    )
    await db.add_proposal_contribution(
        proposal_id=fed2_id, contributor_name="Sarah",
        original_rule_text="Always pin exact versions for Python packages to avoid surprise breakage",
        original_confidence=0.85, source_excerpt="Same issue with numpy update breaking tests", similarity_score=0.78,
    )
    await db.update_proposal_confidence(fed2_id, consensus_confidence(0.82, 2), 2)
    if repo_id:
        await db.update_proposal_repo_id(fed2_id, repo_id)

    logger.info("Demo data seeded successfully")


# --------------- App Lifecycle ---------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    await db.init_db()
    await seed_demo_data()
    logger.info("Tacit backend started")
    yield
    logger.info("Tacit backend shutting down")


app = FastAPI(
    title="Tacit",
    description="Extract team knowledge from GitHub PRs and Claude Code conversations",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------- Request Models ---------------

class RepoCreate(BaseModel):
    owner: str
    name: str
    github_token: str = ""


class ExtractRequest(BaseModel):
    github_token: str | None = None


class ProposalCreate(BaseModel):
    rule_text: str
    category: str = "general"
    confidence: float = 0.8
    source_excerpt: str = ""
    proposed_by: str = ""


class ProposalReview(BaseModel):
    status: str  # "approved" or "rejected"
    feedback: str = ""
    reviewed_by: str = ""


class FeedbackRequest(BaseModel):
    vote: str  # "up" or "down"


class LocalExtractRequest(BaseModel):
    project_path: str


class ContributedRule(BaseModel):
    rule_text: str
    category: str = "general"
    confidence: float = 0.8
    source_excerpt: str = ""


class ContributionPayload(BaseModel):
    contributor_name: str
    rules: list[ContributedRule]
    project_hint: str = ""  # "owner/repo" from git remote
    client_version: str = ""


class HookCaptureRequest(BaseModel):
    transcript_path: str
    cwd: str = ""
    session_id: str = ""


class OnboardingRequest(BaseModel):
    developer_name: str
    role: str = "developer"
    repo_ids: list[int] = []
    focus_categories: list[str] = []


# --------------- Helpers ---------------


def consensus_confidence(base: float, contributor_count: int) -> float:
    """base + 0.08 * log2(count), capped at 0.98"""
    if contributor_count <= 1:
        return base
    return min(0.98, base + 0.08 * math.log2(contributor_count))


# --------------- Repository Endpoints ---------------

@app.post("/api/repos")
async def connect_repo(body: RepoCreate):
    """Connect a GitHub repository for knowledge extraction."""
    repo = await db.create_repo(body.owner, body.name, github_token=body.github_token)
    return repo


@app.get("/api/repos")
async def list_repos():
    """List all connected repositories."""
    return await db.list_repos()


# --------------- Extraction Endpoints ---------------

@app.post("/api/extract/{repo_id}")
async def start_extraction(repo_id: int, body: ExtractRequest | None = None):
    """Start knowledge extraction for a repository. Returns run ID. Stream progress via WebSocket."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    token = (body.github_token if body else None) or repo.get("github_token") or settings.GITHUB_TOKEN
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token required. Set GITHUB_TOKEN env var or pass in request.")

    run = await db.create_extraction_run(repo_id)

    # Start extraction in background
    asyncio.create_task(_extraction_background(repo["full_name"], token, run["id"]))

    return {"run_id": run["id"], "status": "started", "message": "Connect to /ws for live progress"}


async def _extraction_background(repo: str, token: str, run_id: int) -> None:
    """Run extraction in background and broadcast events to WebSocket clients."""
    try:
        async for event in run_extraction(repo, token):
            # Broadcast to all connected WebSocket clients
            await broadcast_event(event)
    except Exception as e:
        logger.exception(f"Background extraction error: {e}")
        await broadcast_event(ExtractionEvent(
            event_type="error", stage="error", message=str(e),
        ))


# --------------- Knowledge Endpoints ---------------

@app.get("/api/knowledge")
async def list_knowledge(
    category: str | None = Query(None),
    repo_id: int | None = Query(None),
    q: str | None = Query(None),
):
    """List knowledge rules with optional filters."""
    if q:
        return await db.search_rules(q, category=category, repo_id=repo_id)
    return await db.list_rules(category=category, repo_id=repo_id)


@app.get("/api/knowledge/cross-repo")
async def get_cross_repo_patterns():
    """Find shared knowledge patterns across repositories."""
    from difflib import SequenceMatcher

    all_rules = await db.list_rules()
    all_repos = await db.list_repos()
    repo_map = {r["id"]: r["full_name"] for r in all_repos}

    # Group rules by category and find similar ones across repos
    by_category: dict[str, list[dict]] = {}
    for rule in all_rules:
        cat = rule.get("category", "general")
        by_category.setdefault(cat, []).append(rule)

    org_patterns = []
    seen = set()

    for category, rules in by_category.items():
        for i, r1 in enumerate(rules):
            if r1["id"] in seen:
                continue
            group = [r1]
            repos_set = {repo_map.get(r1.get("repo_id"), "unknown")}

            for r2 in rules[i + 1:]:
                if r2["id"] in seen:
                    continue
                similarity = SequenceMatcher(
                    None, r1["rule_text"].lower(), r2["rule_text"].lower()
                ).ratio()
                if similarity > 0.6:
                    group.append(r2)
                    repos_set.add(repo_map.get(r2.get("repo_id"), "unknown"))
                    seen.add(r2["id"])

            if len(repos_set) > 1:
                seen.add(r1["id"])
                org_patterns.append({
                    "rule_text": r1["rule_text"],
                    "repos": sorted(repos_set),
                    "frequency": len(group),
                    "category": category,
                })

    org_patterns.sort(key=lambda p: p["frequency"], reverse=True)
    return {"org_patterns": org_patterns}


@app.get("/api/knowledge/{rule_id}")
async def get_knowledge(rule_id: int):
    """Get a knowledge rule with its full decision trail."""
    rule = await db.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    trail = await db.get_trail_for_rule(rule_id)
    return {"rule": rule, "decision_trail": trail}


@app.post("/api/knowledge/{rule_id}/feedback")
async def submit_feedback(rule_id: int, body: FeedbackRequest):
    """Submit feedback (upvote/downvote) for a knowledge rule."""
    rule = await db.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    delta = 1 if body.vote == "up" else -1
    updated = await db.update_feedback_score(rule_id, delta)
    return updated


@app.get("/api/stats/source-quality")
async def get_source_quality():
    """Get aggregated quality stats by source type."""
    stats = await db.get_source_quality_stats()
    return {"source_quality": stats}


# --------------- Proposal Endpoints ---------------

@app.post("/api/proposals")
async def create_proposal(body: ProposalCreate):
    """Create a new knowledge rule proposal."""
    return await prop.create_proposal(
        rule_text=body.rule_text,
        category=body.category,
        confidence=body.confidence,
        source_excerpt=body.source_excerpt,
        proposed_by=body.proposed_by,
    )


@app.get("/api/proposals")
async def list_proposals(status: str | None = Query(None)):
    """List proposals, optionally filtered by status."""
    return await prop.list_proposals(status=status)


@app.put("/api/proposals/{proposal_id}")
async def review_proposal(proposal_id: int, body: ProposalReview):
    """Approve or reject a proposal."""
    if body.status == "approved":
        result = await prop.approve_proposal(proposal_id, body.reviewed_by, body.feedback)
    elif body.status == "rejected":
        result = await prop.reject_proposal(proposal_id, body.reviewed_by, body.feedback)
    else:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    if not result:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return result


# --------------- Federated Contribution ---------------

@app.post("/api/contribute")
async def contribute_rules(body: ContributionPayload):
    """Accept federated contributions from developers' local extractions."""
    # Resolve project_hint → repo_id
    repo_id = None
    if body.project_hint:
        repos = await db.list_repos()
        for r in repos:
            if r["full_name"] == body.project_hint:
                repo_id = r["id"]
                break

    results = []
    pending_proposals = await db.find_similar_pending_proposals("")

    for rule in body.rules:
        # Find semantically similar pending proposal (Claude-powered)
        best_match, best_score = await find_semantic_match(rule.rule_text, pending_proposals)

        if best_match:
            # Merge into existing proposal
            proposal_id = best_match["id"]
            await db.add_proposal_contribution(
                proposal_id=proposal_id,
                contributor_name=body.contributor_name,
                original_rule_text=rule.rule_text,
                original_confidence=rule.confidence,
                source_excerpt=rule.source_excerpt,
                similarity_score=best_score,
            )
            count = await db.get_contribution_count(proposal_id)
            new_confidence = consensus_confidence(best_match["confidence"], count)
            await db.update_proposal_confidence(proposal_id, new_confidence, count)
            if repo_id:
                await db.update_proposal_repo_id(proposal_id, repo_id)
            results.append({
                "action": "merged",
                "proposal_id": proposal_id,
                "contributor_count": count,
                "similarity_score": round(best_score, 2),
            })
        else:
            # Create new proposal
            new_proposal = await db.create_proposal(
                rule_text=rule.rule_text,
                category=rule.category,
                confidence=rule.confidence,
                source_excerpt=rule.source_excerpt,
                proposed_by=body.contributor_name,
            )
            proposal_id = new_proposal["id"]
            # Record initial contribution
            await db.add_proposal_contribution(
                proposal_id=proposal_id,
                contributor_name=body.contributor_name,
                original_rule_text=rule.rule_text,
                original_confidence=rule.confidence,
                source_excerpt=rule.source_excerpt,
                similarity_score=1.0,
            )
            if repo_id:
                await db.update_proposal_repo_id(proposal_id, repo_id)
            # Add to pending list for subsequent rules in this batch
            pending_proposals.append(new_proposal)
            results.append({
                "action": "created",
                "proposal_id": proposal_id,
                "contributor_count": 1,
            })

    # Broadcast WebSocket event
    await broadcast_event(ExtractionEvent(
        event_type="progress",
        stage="contribution",
        message=f"{body.contributor_name} contributed {len(body.rules)} rule(s)",
        data={"contributor": body.contributor_name, "count": len(body.rules)},
    ))

    return {"accepted": len(results), "results": results}


@app.get("/api/proposals/{proposal_id}/contributions")
async def get_proposal_contributions(proposal_id: int):
    """List contribution history for a proposal."""
    proposal = await db.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    contributions = await db.list_proposal_contributions(proposal_id)
    return {"proposal_id": proposal_id, "contributions": contributions}


# --------------- CLAUDE.md Generation ---------------

@app.get("/api/claude-md/{repo_id}")
async def get_claude_md(repo_id: int):
    """Generate CLAUDE.md content from the knowledge base for a repository."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    content = await generate_claude_md(repo_id)
    return {"repo": repo["full_name"], "content": content}


@app.get("/api/claude-md/{repo_id}/diff")
async def get_claude_md_diff(repo_id: int):
    """Compare the existing CLAUDE.md on GitHub with a newly generated one."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    github_token = repo.get("github_token") or settings.GITHUB_TOKEN
    full_name = repo["full_name"]

    # Fetch existing CLAUDE.md from GitHub
    existing = ""
    async with httpx.AsyncClient() as client:
        headers = {
            "Accept": "application/vnd.github.v3.raw",
            "Authorization": f"Bearer {github_token}",
        }
        resp = await client.get(
            f"https://api.github.com/repos/{full_name}/contents/CLAUDE.md",
            headers=headers,
        )
        if resp.status_code == 200:
            existing = resp.text
        elif resp.status_code != 404:
            logger.warning(f"GitHub API returned {resp.status_code} fetching CLAUDE.md for {full_name}")

    # Generate new CLAUDE.md
    generated = await generate_claude_md(repo_id)

    # Compute unified diff
    existing_lines = existing.splitlines(keepends=True)
    generated_lines = generated.splitlines(keepends=True)
    diff = difflib.unified_diff(existing_lines, generated_lines, fromfile="CLAUDE.md (current)", tofile="CLAUDE.md (generated)")

    diff_lines = []
    for line in diff:
        stripped = line.rstrip("\n")
        if stripped.startswith("+"):
            diff_lines.append({"type": "add", "text": stripped})
        elif stripped.startswith("-"):
            diff_lines.append({"type": "remove", "text": stripped})
        else:
            diff_lines.append({"type": "context", "text": stripped})

    return {
        "existing": existing,
        "generated": generated,
        "diff_lines": diff_lines,
    }


class CreatePRRequest(BaseModel):
    content: str
    branch_name: str = "tacit/update-claude-md"
    commit_message: str = "Update CLAUDE.md via Tacit"
    pr_title: str = "Update CLAUDE.md with extracted team knowledge"
    pr_body: str = "This PR updates CLAUDE.md based on knowledge extracted by Tacit from PR reviews, CI fixes, documentation, and code analysis."


@app.post("/api/claude-md/{repo_id}/create-pr")
async def create_claude_md_pr(repo_id: int, body: CreatePRRequest):
    """Create a GitHub PR with generated CLAUDE.md content."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    token = repo.get("github_token") or settings.GITHUB_TOKEN
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token required for PR creation")

    full_name = repo["full_name"]
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    import base64

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. Get default branch
        repo_resp = await client.get(
            f"https://api.github.com/repos/{full_name}",
            headers=headers, timeout=15,
        )
        if repo_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {repo_resp.status_code}")
        default_branch = repo_resp.json().get("default_branch", "main")

        # 2. Get default branch SHA
        ref_resp = await client.get(
            f"https://api.github.com/repos/{full_name}/git/ref/heads/{default_branch}",
            headers=headers, timeout=15,
        )
        if ref_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not get branch SHA")
        base_sha = ref_resp.json()["object"]["sha"]

        # 3. Create branch
        branch_ref = f"refs/heads/{body.branch_name}"
        create_ref_resp = await client.post(
            f"https://api.github.com/repos/{full_name}/git/refs",
            headers=headers, timeout=15,
            json={"ref": branch_ref, "sha": base_sha},
        )
        if create_ref_resp.status_code not in (201, 422):  # 422 = branch exists
            raise HTTPException(status_code=502, detail=f"Could not create branch: {create_ref_resp.text}")

        # 4. Check if CLAUDE.md exists (to get its SHA for update)
        file_sha = None
        existing_resp = await client.get(
            f"https://api.github.com/repos/{full_name}/contents/CLAUDE.md",
            headers=headers, timeout=15,
            params={"ref": body.branch_name},
        )
        if existing_resp.status_code == 200:
            file_sha = existing_resp.json().get("sha")

        # 5. Create/update CLAUDE.md
        content_b64 = base64.b64encode(body.content.encode()).decode()
        put_body: dict = {
            "message": body.commit_message,
            "content": content_b64,
            "branch": body.branch_name,
        }
        if file_sha:
            put_body["sha"] = file_sha

        put_resp = await client.put(
            f"https://api.github.com/repos/{full_name}/contents/CLAUDE.md",
            headers=headers, timeout=15,
            json=put_body,
        )
        if put_resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Could not commit file: {put_resp.text}")

        # 6. Create PR
        pr_resp = await client.post(
            f"https://api.github.com/repos/{full_name}/pulls",
            headers=headers, timeout=15,
            json={
                "title": body.pr_title,
                "body": body.pr_body,
                "head": body.branch_name,
                "base": default_branch,
            },
        )
        if pr_resp.status_code != 201:
            raise HTTPException(status_code=502, detail=f"Could not create PR: {pr_resp.text}")

        pr_data = pr_resp.json()
        return {
            "pr_url": pr_data["html_url"],
            "pr_number": pr_data["number"],
            "branch_name": body.branch_name,
        }


# --------------- Modular Rules Generation ---------------

@app.get("/api/claude-rules/{repo_id}")
async def get_modular_rules(repo_id: int):
    """Generate a .claude/rules/ directory structure from the knowledge base."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    files = await generate_modular_rules(repo_id)
    return {"repo": repo["full_name"], "files": files, "file_count": len(files)}


# --------------- Outcome Metrics ---------------

@app.get("/api/metrics/{repo_id}")
async def get_outcome_metrics(repo_id: int, limit: int = Query(12)):
    """Get historical outcome metrics for a repository."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    metrics = await db.list_outcome_metrics(repo_id, limit=limit)
    rules_count = len(await db.list_rules(repo_id=repo_id))

    # Compute trend if we have at least 2 data points
    trend = {}
    if len(metrics) >= 2:
        latest = metrics[0]
        previous = metrics[1]
        for key in ["pr_revision_rounds", "ci_failure_rate", "review_comment_density", "time_to_merge_hours"]:
            prev_val = previous.get(key, 0)
            curr_val = latest.get(key, 0)
            if prev_val > 0:
                trend[key] = round((curr_val - prev_val) / prev_val * 100, 1)

    return {
        "repo": repo["full_name"],
        "rules_deployed": rules_count,
        "metrics": metrics,
        "trend": trend,
    }


@app.post("/api/metrics/{repo_id}/collect")
async def collect_metrics(repo_id: int):
    """Trigger outcome metrics collection for a repository."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    token = repo.get("github_token") or settings.GITHUB_TOKEN
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token required")

    metrics = await collect_outcome_metrics(repo["full_name"], token, repo_id)

    if metrics:
        from datetime import datetime, timezone, timedelta
        # Use Monday of current week as week_start
        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        rules_count = len(await db.list_rules(repo_id=repo_id))

        await db.upsert_outcome_metrics(
            repo_id=repo_id,
            week_start=week_start,
            pr_revision_rounds=metrics.get("avg_review_rounds", 0),
            ci_failure_rate=metrics.get("ci_failure_rate", 0),
            review_comment_density=metrics.get("avg_comments_per_pr", 0),
            time_to_merge_hours=metrics.get("avg_time_to_merge_hours", 0),
            first_timer_time_to_merge_hours=metrics.get("first_timer_avg_ttm_hours", 0),
            rules_deployed=rules_count,
        )

    return {"collected": True, "metrics": metrics}


# --------------- Local Extraction ---------------

@app.post("/api/local-extract")
async def local_extract(body: LocalExtractRequest):
    """Extract knowledge from local Claude Code conversation logs."""
    events = []
    async for event in run_local_extraction(body.project_path):
        events.append(event.model_dump())
        await broadcast_event(event)
    return {"events": events}


# --------------- Webhook ---------------

class WebhookPayload(BaseModel):
    class Config:
        extra = "allow"


@app.post("/api/webhook/github")
async def github_webhook(request: Request):
    """Handle GitHub webhook events for continuous learning."""
    import hmac
    import hashlib

    # Optional HMAC verification
    webhook_secret = settings.WEBHOOK_SECRET
    if webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        body_bytes = await request.body()
        expected = "sha256=" + hmac.new(
            webhook_secret.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        payload = json.loads(body_bytes)
    else:
        payload = await request.json()

    # Only handle merged pull requests
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    if action != "closed" or not pr.get("merged"):
        return {"ignored": True, "reason": "Not a merged PR event"}

    # Look up repo
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == repo_full_name:
            repo_record = r
            break

    if not repo_record:
        return {"ignored": True, "reason": "Repo not tracked"}

    pr_number = pr.get("number")
    token = repo_record.get("github_token") or settings.GITHUB_TOKEN

    # Run single PR extraction in background
    asyncio.create_task(
        _webhook_extraction_background(repo_full_name, pr_number, token)
    )

    return {"accepted": True, "pr_number": pr_number, "repo": repo_full_name}


async def _webhook_extraction_background(repo: str, pr_number: int, token: str):
    """Run incremental PR extraction from webhook and broadcast events."""
    try:
        result = await incremental_extract(repo, pr_number, token)
        new_rules = result.get("new_rules", 0)
        new_proposals = result.get("new_proposals", 0)
        msg = f"Webhook: PR #{pr_number} in {repo} → {new_rules} auto-approved rules, {new_proposals} proposals"
        await broadcast_event(ExtractionEvent(
            event_type="progress",
            stage="webhook",
            message=msg,
            data={
                "pr_number": pr_number,
                "new_rules": new_rules,
                "new_proposals": new_proposals,
            },
        ))
    except Exception as e:
        logger.exception(f"Webhook extraction error: {e}")
        await broadcast_event(ExtractionEvent(
            event_type="error",
            stage="webhook",
            message=f"Webhook extraction failed for PR #{pr_number}: {str(e)}",
        ))


# --------------- Team Members ---------------

@app.get("/api/team")
async def list_team():
    """List all team members."""
    return await db.list_team_members()


# --------------- WebSocket ---------------

connected_clients: set[WebSocket] = set()


EVENT_TYPE_MAP = {
    "stage_change": "info",
    "rule_found": "rule_discovered",
    "progress": "analyzing",
    "complete": "stage_complete",
    "error": "error",
}


async def broadcast_event(event: ExtractionEvent) -> None:
    """Broadcast an extraction event to all connected WebSocket clients.

    Transforms backend ExtractionEvent into the wire format expected by the Swift frontend:
    - Renames event_type → type with value mapping
    - Merges message into data dict
    - Stringifies all data values for Swift [String: String] compatibility
    - Special case: complete → stage_complete with data.stage = "done"
    """
    mapped_type = EVENT_TYPE_MAP.get(event.event_type, "info")

    # Build data dict: merge event.data + message, stringify all values
    wire_data: dict[str, str] = {}
    if event.data:
        for k, v in event.data.items():
            wire_data[k] = str(v)
    if event.message:
        wire_data["message"] = event.message
    if event.stage:
        wire_data["stage"] = event.stage

    # Special case: complete → stage_complete with stage="done"
    if event.event_type == "complete":
        wire_data["stage"] = "done"

    wire = json.dumps({
        "type": mapped_type,
        "data": wire_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    disconnected = set()
    for ws in connected_clients:
        try:
            await ws.send_text(wire)
        except Exception:
            disconnected.add(ws)
    connected_clients.difference_update(disconnected)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for streaming extraction events."""
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")
    try:
        while True:
            # Keep connection alive; clients send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(connected_clients)}")


# --------------- PR Validation ---------------

@app.post("/api/validate-pr")
async def validate_pr(body: PRValidationRequest):
    """Validate a PR against knowledge rules."""
    # Find repo
    repos = await db.list_repos()
    repo_record = None
    for r in repos:
        if r["full_name"] == body.repo:
            repo_record = r
            break

    repo_id = repo_record["id"] if repo_record else None

    # Check if there are any rules to validate against
    existing_rules = await db.list_rules(repo_id=repo_id)
    if not existing_rules:
        return PRValidationResult(
            violations=[],
            total=0,
            files_checked=0,
        )

    # Run pr-validator agent
    from pipeline import _run_agent
    validator_prompt = (
        f"Validate PR #{body.pr_number} in repository '{body.repo}' against knowledge rules. "
        f"Use github_fetch_pr_diff with repo='{body.repo}', pr_number={body.pr_number}, github_token='{body.github_token}'. "
        f"Use list_all_knowledge with repo_id={repo_id} to get all rules. "
        f"Return a JSON array of violations."
    )
    result_text = await _run_agent("pr-validator", validator_prompt, repo_id)

    # Parse violations from agent output
    violations = []
    try:
        import re as _re
        # Find JSON array in the output
        match = _re.search(r'\[.*\]', result_text, _re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            for v in parsed:
                violations.append(RuleViolation(
                    rule_id=v.get("rule_id", 0),
                    rule_text=v.get("rule_text", ""),
                    file=v.get("file", ""),
                    reason=v.get("reason", ""),
                ))
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Could not parse validation result: {e}")

    return PRValidationResult(
        violations=violations,
        total=len(violations),
        files_checked=0,
    )


@app.post("/api/validate-pr/post-review")
async def post_pr_review(body: dict):
    """Post validation results as a GitHub PR review comment."""
    repo = body.get("repo", "")
    pr_number = body.get("pr_number", 0)
    token = body.get("github_token", "")
    violations = body.get("violations", [])

    if not violations:
        return {"message": "No violations to post"}

    # Format review body with provenance
    review_body = "## Tacit Knowledge Review\n\n"
    review_body += f"Found **{len(violations)}** potential rule violation(s):\n\n"
    for v in violations:
        review_body += f"- **{v.get('file', 'unknown')}**: {v.get('reason', '')}\n"
        review_body += f"  - Rule: _{v.get('rule_text', '')}_\n"
        # Include provenance if available
        rule_id = v.get("rule_id")
        if rule_id:
            rule = await db.get_rule(rule_id)
            if rule and rule.get("provenance_url"):
                review_body += f"  - Why: {rule.get('provenance_summary', 'See source')} "
                review_body += f"([source]({rule['provenance_url']}))\n"
        review_body += "\n"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews",
            headers=headers, timeout=15,
            json={
                "body": review_body,
                "event": "COMMENT",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")

        review_data = resp.json()
        return {
            "review_id": review_data.get("id"),
            "review_url": review_data.get("html_url", ""),
        }


# --------------- Hooks (Feature 1) ---------------

@app.post("/api/hooks/capture")
async def hooks_capture(body: HookCaptureRequest):
    """Receive a session transcript from the Claude Code hook and mine it for knowledge."""
    asyncio.create_task(_hook_capture_background(body.transcript_path, body.cwd))
    return {"accepted": True, "transcript_path": body.transcript_path}


async def _hook_capture_background(transcript_path: str, cwd: str):
    """Mine a session transcript in the background (called by hook)."""
    try:
        result = await mine_session(transcript_path, cwd)
        if result.get("rules_found", 0) > 0:
            await broadcast_event(ExtractionEvent(
                event_type="progress",
                stage="hook_capture",
                message=f"Hook captured {result['rules_found']} rule(s) from session",
                data={"rules_found": result["rules_found"], "path": transcript_path},
            ))
    except Exception as e:
        logger.exception(f"Hook capture error: {e}")


@app.get("/api/hooks/config")
async def hooks_config():
    """Return a ready-to-use Claude Code hook configuration JSON."""
    import os
    hook_script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "hooks", "tacit-capture.sh")
    )
    config = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_script,
                            "timeout": 30,
                        }
                    ]
                }
            ]
        }
    }
    return {"config": config, "hook_script_path": hook_script}


@app.get("/api/hooks/status")
async def hooks_status():
    """Check whether the hook script exists and is executable."""
    import os
    hook_script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "hooks", "tacit-capture.sh")
    )
    exists = os.path.isfile(hook_script)
    executable = os.access(hook_script, os.X_OK) if exists else False

    # Check if Claude Code settings reference our hook
    settings_path = os.path.expanduser("~/.claude/settings.json")
    installed = False
    if os.path.isfile(settings_path):
        try:
            with open(settings_path) as f:
                claude_settings = json.load(f)
            hooks = claude_settings.get("hooks", {})
            stop_hooks = hooks.get("Stop", [])
            for hook_group in stop_hooks:
                for hook in hook_group.get("hooks", []):
                    if hook.get("command", "").endswith("tacit-capture.sh"):
                        installed = True
                        break
        except (json.JSONDecodeError, IOError):
            pass

    # Get recently captured rules
    recent_sessions = await db.list_mined_sessions()

    return {
        "hook_script_exists": exists,
        "hook_script_executable": executable,
        "hook_script_path": hook_script,
        "installed_in_settings": installed,
        "recent_captures": recent_sessions[:10],
    }


@app.post("/api/hooks/install")
async def hooks_install():
    """Install the hook script into Claude Code settings."""
    import os
    hook_script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "hooks", "tacit-capture.sh")
    )

    # Ensure hook script exists and is executable
    if not os.path.isfile(hook_script):
        raise HTTPException(status_code=500, detail="Hook script not found")
    os.chmod(hook_script, 0o755)

    # Read or create Claude Code settings
    settings_path = os.path.expanduser("~/.claude/settings.json")
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    claude_settings = {}
    if os.path.isfile(settings_path):
        try:
            with open(settings_path) as f:
                claude_settings = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Add hook config
    hooks = claude_settings.setdefault("hooks", {})
    stop_hooks = hooks.setdefault("Stop", [])

    # Check if already installed
    already_installed = False
    for hook_group in stop_hooks:
        for hook in hook_group.get("hooks", []):
            if hook.get("command", "").endswith("tacit-capture.sh"):
                already_installed = True
                break

    if not already_installed:
        stop_hooks.append({
            "hooks": [
                {
                    "type": "command",
                    "command": hook_script,
                    "timeout": 30,
                }
            ]
        })

    # Prevent conversation cleanup (preserve transcripts for mining)
    claude_settings["cleanupPeriodDays"] = 99999

    with open(settings_path, "w") as f:
        json.dump(claude_settings, f, indent=2)

    return {
        "installed": True,
        "hook_script_path": hook_script,
        "settings_path": settings_path,
        "cleanup_disabled": True,
    }


# --------------- Session Mining (Feature 2) ---------------

@app.post("/api/mine-sessions")
async def mine_sessions_endpoint():
    """Scan all Claude Code sessions and extract knowledge from transcripts."""
    results = await mine_all_sessions()

    total_rules = sum(r.get("rules_found", 0) for r in results)
    skipped = sum(1 for r in results if r.get("skipped"))

    await broadcast_event(ExtractionEvent(
        event_type="progress",
        stage="session_mining",
        message=f"Mined {len(results)} sessions, found {total_rules} rules ({skipped} skipped)",
        data={"sessions": len(results), "rules_found": total_rules, "skipped": skipped},
    ))

    return {
        "sessions_processed": len(results),
        "sessions_skipped": skipped,
        "total_rules_found": total_rules,
        "results": results,
    }


@app.get("/api/sessions")
async def list_sessions():
    """List discovered sessions with metadata."""
    sessions = await db.list_mined_sessions()
    return {"sessions": sessions, "total": len(sessions)}


# --------------- Auto-Onboarding (Feature 4) ---------------

@app.post("/api/onboarding/generate")
async def generate_onboarding(body: OnboardingRequest):
    """Generate a personalized onboarding guide for a new developer."""
    # Gather all rules for the specified repos
    all_rules = []
    if body.repo_ids:
        for repo_id in body.repo_ids:
            rules = await db.list_rules(repo_id=repo_id)
            all_rules.extend(rules)
    else:
        all_rules = await db.list_rules()

    # Filter by focus categories if specified
    if body.focus_categories:
        all_rules = [r for r in all_rules if r["category"] in body.focus_categories]

    if not all_rules:
        return {
            "developer_name": body.developer_name,
            "role": body.role,
            "content": f"# Onboarding Guide for {body.developer_name}\n\nNo knowledge rules found for the specified repositories. Run an extraction first.",
            "sections": [],
        }

    # Try Claude-powered personalization
    content = None
    if settings.ANTHROPIC_API_KEY:
        try:
            content = await _generate_onboarding_with_claude(body, all_rules)
        except Exception as e:
            logger.warning(f"Claude onboarding generation failed, using template: {e}")

    # Fallback: template-based generation
    if not content:
        content = _generate_onboarding_template(body, all_rules)

    return {
        "developer_name": body.developer_name,
        "role": body.role,
        "content": content,
        "rule_count": len(all_rules),
    }


async def _generate_onboarding_with_claude(body: OnboardingRequest, rules: list[dict]) -> str | None:
    """Use Claude to generate a personalized onboarding guide."""
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock

    rules_text = json.dumps([
        {"rule_text": r["rule_text"], "category": r["category"],
         "confidence": r["confidence"], "source_type": r["source_type"],
         "feedback_score": r.get("feedback_score", 0)}
        for r in rules
    ], indent=2)

    system_prompt = (
        "You are an onboarding guide generator. Given a set of team knowledge rules "
        "and a new developer's profile, create a warm, structured onboarding document. "
        "Organize rules into three tiers: Critical (must know), Important (should know), "
        "and Good to Know. Group by category. Write natural intro paragraphs. "
        "Highlight potential gotchas. Use markdown formatting."
    )

    user_prompt = (
        f"Generate an onboarding guide for {body.developer_name} "
        f"(role: {body.role}).\n\n"
        f"Team knowledge rules:\n{rules_text}\n\n"
        f"Focus categories: {body.focus_categories or 'all'}\n\n"
        f"Create a structured onboarding document with:\n"
        f"1. Welcome section mentioning their role\n"
        f"2. Critical rules (confidence >= 0.9 or feedback_score >= 3)\n"
        f"3. Important conventions (confidence >= 0.7)\n"
        f"4. Good to know (the rest)\n"
        f"5. Common gotchas section\n"
        f"Use markdown formatting."
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model="sonnet",
        mcp_servers={},
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=1,
    )

    result_text = []
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        await client.query(user_prompt)
        async for message in client.receive_response():
            if isinstance(message, ResultMessage) and message.is_error:
                logger.error(f"Onboarding generation error: {message.result}")
                return None
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text.append(block.text)
    finally:
        await client.disconnect()

    return "\n".join(result_text)


def _generate_onboarding_template(body: OnboardingRequest, rules: list[dict]) -> str:
    """Generate a template-based onboarding document (fallback)."""
    lines = [
        f"# Onboarding Guide for {body.developer_name}",
        f"\nWelcome to the team, {body.developer_name}! As a **{body.role}**, "
        f"here's what you need to know based on our team's extracted knowledge.\n",
    ]

    # Categorize rules into tiers
    critical = [r for r in rules if r["confidence"] >= 0.9 or r.get("feedback_score", 0) >= 3]
    important = [r for r in rules if r not in critical and r["confidence"] >= 0.7]
    good_to_know = [r for r in rules if r not in critical and r not in important]

    def _section(title: str, tier_rules: list[dict]):
        if not tier_rules:
            return
        lines.append(f"\n## {title}\n")
        by_category: dict[str, list[dict]] = {}
        for r in tier_rules:
            by_category.setdefault(r["category"], []).append(r)
        for cat, cat_rules in sorted(by_category.items()):
            lines.append(f"\n### {cat.title()}\n")
            for r in sorted(cat_rules, key=lambda x: -x["confidence"]):
                conf = f" *(confidence: {r['confidence']:.0%})*"
                lines.append(f"- {r['rule_text']}{conf}")

    _section("Critical — You Must Know These", critical)
    _section("Important — Your Team Expects These", important)
    _section("Good to Know — Context for Later", good_to_know)

    lines.append("\n---\n*Generated by Tacit from team knowledge rules.*\n")
    return "\n".join(lines)


# --------------- Health Dashboard ---------------

@app.get("/api/health")
async def health():
    """Comprehensive health check with system status."""
    import os

    # Check hook installation
    hook_script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "hooks", "tacit-capture.sh")
    )
    hook_installed = False
    settings_path = os.path.expanduser("~/.claude/settings.json")
    if os.path.isfile(settings_path):
        try:
            with open(settings_path) as f:
                claude_settings = json.load(f)
            for hook_group in claude_settings.get("hooks", {}).get("Stop", []):
                for hook in hook_group.get("hooks", []):
                    if hook.get("command", "").endswith("tacit-capture.sh"):
                        hook_installed = True
        except (json.JSONDecodeError, IOError):
            pass

    # Count data
    repos = await db.list_repos()
    all_rules = await db.list_rules()
    pending_proposals = await db.list_proposals(status="pending")
    sessions = await db.list_mined_sessions()

    # Rules by source type
    source_counts: dict[str, int] = {}
    for rule in all_rules:
        st = rule.get("source_type", "unknown")
        source_counts[st] = source_counts.get(st, 0) + 1

    return {
        "status": "ok",
        "version": "2.0.0",
        "repositories": len(repos),
        "total_rules": len(all_rules),
        "rules_by_source": source_counts,
        "pending_proposals": len(pending_proposals),
        "sessions_mined": len(sessions),
        "hook_installed": hook_installed,
        "hook_script_exists": os.path.isfile(hook_script),
        "agents": 14,  # 11 original + 3 new
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

"""FastAPI application with REST endpoints and WebSocket for Tacit."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
import proposals as prop
from pipeline import run_extraction, run_local_extraction, generate_claude_md
from config import settings
from models import ExtractionEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------- Seed Data ---------------

async def seed_demo_data() -> None:
    """Seed the database with demo team members and sample proposals."""
    # Team members
    await db.create_team_member("Bayram", "🎯", "team lead")
    await db.create_team_member("Alex", "⚡", "frontend dev")
    await db.create_team_member("Sarah", "🔧", "backend dev")

    # Check if we already have proposals (avoid duplicates on restart)
    existing = await db.list_proposals()
    if len(existing) > 0:
        return

    # Sample proposals from Alex
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

    # Sample proposal from Sarah
    await db.create_proposal(
        rule_text="All API endpoints must return structured error responses with error_code and message fields",
        category="architecture",
        confidence=0.92,
        source_excerpt="Sarah: 'Inconsistent error formats caused 3 frontend bugs last sprint. Standardizing on {error_code, message} format.'",
        proposed_by="Sarah",
    )

    # Create a sample repository
    await db.create_repo("anthropics", "claude-code")

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


class LocalExtractRequest(BaseModel):
    project_path: str


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


@app.get("/api/knowledge/{rule_id}")
async def get_knowledge(rule_id: int):
    """Get a knowledge rule with its full decision trail."""
    rule = await db.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    trail = await db.get_trail_for_rule(rule_id)
    return {"rule": rule, "decision_trail": trail}


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


# --------------- CLAUDE.md Generation ---------------

@app.get("/api/claude-md/{repo_id}")
async def get_claude_md(repo_id: int):
    """Generate CLAUDE.md content from the knowledge base for a repository."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    content = await generate_claude_md(repo_id)
    return {"repo": repo["full_name"], "content": content}


# --------------- Local Extraction ---------------

@app.post("/api/local-extract")
async def local_extract(body: LocalExtractRequest):
    """Extract knowledge from local Claude Code conversation logs."""
    events = []
    async for event in run_local_extraction(body.project_path):
        events.append(event.model_dump())
        await broadcast_event(event)
    return {"events": events}


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


# --------------- Health ---------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

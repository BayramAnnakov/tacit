"""Pydantic models for API request/response."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RepoConnection(BaseModel):
    """Repository connection configuration."""

    id: int | None = None
    owner: str
    name: str
    full_name: str = ""
    github_url: str = ""
    connected_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.full_name:
            self.full_name = f"{self.owner}/{self.name}"
        if not self.github_url:
            self.github_url = f"https://github.com/{self.full_name}"


class TeamMember(BaseModel):
    """Team member profile."""

    id: int | None = None
    name: str
    avatar_emoji: str = "👤"
    role: str = "developer"


class KnowledgeRule(BaseModel):
    """An extracted knowledge rule."""

    id: int | None = None
    rule_text: str
    category: str = "general"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_type: Literal["pr", "conversation", "structure", "docs", "ci_fix", "config", "anti_pattern"] = "pr"
    source_ref: str = ""
    repo_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Proposal(BaseModel):
    """A proposed knowledge rule awaiting review."""

    id: int | None = None
    rule_text: str
    category: str = "general"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_excerpt: str = ""
    proposed_by: str = ""
    status: Literal["pending", "approved", "rejected"] = "pending"
    feedback: str = ""
    reviewed_by: str = ""
    created_at: datetime | None = None


class ExtractionRun(BaseModel):
    """Status of an extraction pipeline run."""

    id: int | None = None
    repo_id: int
    status: Literal["running", "completed", "failed"] = "running"
    stage: str = "initializing"
    rules_found: int = 0
    prs_analyzed: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExtractionEvent(BaseModel):
    """Real-time event emitted during extraction for WebSocket streaming."""

    event_type: str  # e.g. "stage_change", "rule_found", "progress", "complete", "error"
    stage: str = ""
    message: str = ""
    data: dict | None = None


class DecisionTrailEntry(BaseModel):
    """An entry in a knowledge rule's decision trail."""

    id: int | None = None
    rule_id: int
    event_type: str  # e.g. "created", "refined", "approved", "rejected"
    description: str = ""
    source_ref: str = ""
    timestamp: datetime | None = None


class PRValidationRequest(BaseModel):
    """Request to validate a PR against knowledge rules."""
    repo: str
    pr_number: int
    github_token: str
    categories: list[str] | None = None


class RuleViolation(BaseModel):
    """A single rule violation found in a PR."""
    rule_id: int
    rule_text: str
    file: str
    reason: str
    provenance_url: str = ""
    provenance_summary: str = ""


class PRValidationResult(BaseModel):
    """Result of PR validation."""
    violations: list[RuleViolation]
    total: int
    files_checked: int

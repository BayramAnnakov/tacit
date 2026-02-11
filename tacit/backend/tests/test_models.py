"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from models import (
    KnowledgeRule,
    RepoConnection,
    ExtractionEvent,
    PRValidationRequest,
    PRValidationResult,
    RuleViolation,
    Proposal,
)


class TestKnowledgeRule:
    def test_defaults(self):
        rule = KnowledgeRule(rule_text="test rule")
        assert rule.category == "general"
        assert rule.confidence == 0.8
        assert rule.source_type == "pr"

    def test_confidence_too_low(self):
        with pytest.raises(ValidationError):
            KnowledgeRule(rule_text="test", confidence=-0.1)

    def test_confidence_too_high(self):
        with pytest.raises(ValidationError):
            KnowledgeRule(rule_text="test", confidence=1.1)

    def test_source_type_invalid(self):
        with pytest.raises(ValidationError):
            KnowledgeRule(rule_text="test", source_type="invalid")

    def test_source_type_ci_fix(self):
        rule = KnowledgeRule(rule_text="test", source_type="ci_fix")
        assert rule.source_type == "ci_fix"

    def test_all_valid_source_types(self):
        for st in ("pr", "conversation", "structure", "docs", "ci_fix", "config"):
            rule = KnowledgeRule(rule_text="test", source_type=st)
            assert rule.source_type == st


class TestRepoConnection:
    def test_auto_full_name(self):
        repo = RepoConnection(owner="acme", name="widgets")
        assert repo.full_name == "acme/widgets"
        assert repo.github_url == "https://github.com/acme/widgets"

    def test_explicit_full_name(self):
        repo = RepoConnection(owner="a", name="b", full_name="custom/name")
        assert repo.full_name == "custom/name"


class TestExtractionEvent:
    def test_data_optional(self):
        event = ExtractionEvent(event_type="progress")
        assert event.data is None

    def test_with_data(self):
        event = ExtractionEvent(event_type="rule_found", data={"count": 5})
        assert event.data == {"count": 5}


class TestPRValidationRequest:
    def test_required_fields(self):
        req = PRValidationRequest(repo="owner/repo", pr_number=42, github_token="tok")
        assert req.repo == "owner/repo"
        assert req.pr_number == 42

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            PRValidationRequest(repo="owner/repo")


class TestPRValidationResult:
    def test_structure(self):
        v = RuleViolation(rule_id=1, rule_text="test", file="a.py", reason="bad")
        result = PRValidationResult(violations=[v], total=1, files_checked=3)
        assert result.total == 1
        assert len(result.violations) == 1
        assert result.files_checked == 3


class TestProposal:
    def test_status_literal(self):
        p = Proposal(rule_text="test", status="approved")
        assert p.status == "approved"

    def test_status_invalid(self):
        with pytest.raises(ValidationError):
            Proposal(rule_text="test", status="maybe")

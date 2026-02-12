"""Tests for federated learning: contributions, consensus, and client script."""

import math
from unittest.mock import AsyncMock, patch

import pytest

import database as db
from main import consensus_confidence, find_semantic_match, _sequencematcher_fallback


# ============================================================
# Unit: consensus_confidence formula
# ============================================================

class TestConsensusConfidence:
    def test_single_contributor(self):
        assert consensus_confidence(0.80, 1) == 0.80

    def test_two_contributors(self):
        # base + 0.08 * log2(2) = 0.80 + 0.08 = 0.88
        result = consensus_confidence(0.80, 2)
        assert abs(result - 0.88) < 0.001

    def test_four_contributors(self):
        # base + 0.08 * log2(4) = 0.80 + 0.16 = 0.96
        result = consensus_confidence(0.80, 4)
        assert abs(result - 0.96) < 0.001

    def test_cap_at_098(self):
        # 8 contributors: 0.90 + 0.08*3 = 1.14 → capped at 0.98
        result = consensus_confidence(0.90, 8)
        assert result == 0.98

    def test_zero_contributors(self):
        # edge: 0 → treated as <= 1
        assert consensus_confidence(0.85, 0) == 0.85

    def test_three_contributors(self):
        # base + 0.08 * log2(3) ≈ 0.80 + 0.1268 ≈ 0.9268
        expected = min(0.98, 0.80 + 0.08 * math.log2(3))
        result = consensus_confidence(0.80, 3)
        assert abs(result - expected) < 0.001


# ============================================================
# Database: proposal_contributions CRUD
# ============================================================

class TestProposalContributionsDB:
    async def test_add_contribution(self):
        p = await db.create_proposal("rule text", "general", 0.8, "excerpt", "Alice")
        c = await db.add_proposal_contribution(
            proposal_id=p["id"],
            contributor_name="Alice",
            original_rule_text="rule text",
            original_confidence=0.8,
            source_excerpt="excerpt",
            similarity_score=1.0,
        )
        assert c["proposal_id"] == p["id"]
        assert c["contributor_name"] == "Alice"
        assert c["similarity_score"] == 1.0

    async def test_list_contributions_empty(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "Bob")
        contribs = await db.list_proposal_contributions(p["id"])
        assert contribs == []

    async def test_list_contributions_multiple(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        await db.add_proposal_contribution(p["id"], "Alice", "rule text A", 0.8)
        await db.add_proposal_contribution(p["id"], "Bob", "rule text B", 0.85)
        await db.add_proposal_contribution(p["id"], "Carol", "rule text C", 0.75)
        contribs = await db.list_proposal_contributions(p["id"])
        assert len(contribs) == 3
        names = [c["contributor_name"] for c in contribs]
        assert "Alice" in names
        assert "Bob" in names
        assert "Carol" in names

    async def test_contribution_count_distinct(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        await db.add_proposal_contribution(p["id"], "Alice", "text1", 0.8)
        await db.add_proposal_contribution(p["id"], "Alice", "text2", 0.82)  # same person
        await db.add_proposal_contribution(p["id"], "Bob", "text3", 0.85)
        count = await db.get_contribution_count(p["id"])
        assert count == 2  # Alice + Bob, not 3

    async def test_contribution_count_zero(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        count = await db.get_contribution_count(p["id"])
        assert count == 0

    async def test_update_proposal_confidence(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        updated = await db.update_proposal_confidence(p["id"], 0.92, 3)
        assert updated["confidence"] == 0.92
        assert updated["contributor_count"] == 3

    async def test_update_proposal_repo_id(self):
        repo = await db.create_repo("owner", "repo")
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        await db.update_proposal_repo_id(p["id"], repo["id"])
        fetched = await db.get_proposal(p["id"])
        assert fetched["repo_id"] == repo["id"]

    async def test_find_similar_pending_proposals(self):
        await db.create_proposal("use async everywhere", "arch", 0.8, "", "Alice")
        await db.create_proposal("prefer sync calls", "arch", 0.7, "", "Bob")
        # Approve one — it should not appear in pending results
        p3 = await db.create_proposal("approved rule", "general", 0.9, "", "Carol")
        await db.update_proposal(p3["id"], "approved")

        pending = await db.find_similar_pending_proposals("")
        assert len(pending) == 2
        statuses = {p["status"] for p in pending}
        assert statuses == {"pending"}

    async def test_contributor_count_default(self):
        """New proposals should have contributor_count = 1 by default."""
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        assert p["contributor_count"] == 1

    async def test_repo_id_default_null(self):
        """New proposals should have repo_id = None by default."""
        p = await db.create_proposal("rule", "general", 0.8, "", "Alice")
        assert p["repo_id"] is None


# ============================================================
# API: POST /api/contribute
# ============================================================

class TestContributeEndpoint:
    async def test_create_new_proposal(self, async_client):
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [
                {"rule_text": "Always use async/await for DB calls", "category": "architecture", "confidence": 0.8}
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["results"][0]["action"] == "created"
        assert data["results"][0]["contributor_count"] == 1

    async def test_merge_similar_rule(self, async_client):
        # First contribution creates a proposal
        resp1 = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [
                {"rule_text": "Always use async/await for database operations", "category": "architecture", "confidence": 0.8}
            ],
        })
        assert resp1.status_code == 200
        proposal_id = resp1.json()["results"][0]["proposal_id"]

        # Second contribution with similar text should merge
        resp2 = await async_client.post("/api/contribute", json={
            "contributor_name": "Bob",
            "rules": [
                {"rule_text": "Use async/await for all database operations", "category": "architecture", "confidence": 0.85}
            ],
        })
        assert resp2.status_code == 200
        result = resp2.json()["results"][0]
        assert result["action"] == "merged"
        assert result["proposal_id"] == proposal_id
        assert result["contributor_count"] == 2

    async def test_dissimilar_creates_separate(self, async_client):
        # First rule
        await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Always use async/await for DB calls", "category": "architecture"}],
        })
        # Completely different rule
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Bob",
            "rules": [{"rule_text": "Pin all npm dependencies to exact versions", "category": "workflow"}],
        })
        assert resp.status_code == 200
        assert resp.json()["results"][0]["action"] == "created"

    async def test_multiple_rules_in_batch(self, async_client):
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [
                {"rule_text": "Use structured logging", "category": "architecture", "confidence": 0.8},
                {"rule_text": "Pin dependency versions", "category": "workflow", "confidence": 0.75},
                {"rule_text": "Run tests before merging", "category": "testing", "confidence": 0.9},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 3

    async def test_project_hint_resolves_repo_id(self, async_client, seeded_repo):
        full_name = seeded_repo["full_name"]
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Use type hints everywhere", "category": "style"}],
            "project_hint": full_name,
        })
        assert resp.status_code == 200
        pid = resp.json()["results"][0]["proposal_id"]
        proposal = await db.get_proposal(pid)
        assert proposal["repo_id"] == seeded_repo["id"]

    async def test_project_hint_unknown_repo(self, async_client):
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Some rule", "category": "general"}],
            "project_hint": "unknown/repo",
        })
        assert resp.status_code == 200
        pid = resp.json()["results"][0]["proposal_id"]
        proposal = await db.get_proposal(pid)
        assert proposal["repo_id"] is None

    async def test_confidence_boost_on_merge(self, async_client):
        # Create initial proposal with confidence 0.80
        resp1 = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Always use async/await for database operations", "confidence": 0.80}],
        })
        pid = resp1.json()["results"][0]["proposal_id"]

        # Merge from second contributor
        await async_client.post("/api/contribute", json={
            "contributor_name": "Bob",
            "rules": [{"rule_text": "Use async/await for all database operations", "confidence": 0.85}],
        })

        proposal = await db.get_proposal(pid)
        # consensus_confidence(0.80, 2) = 0.88
        assert abs(proposal["confidence"] - 0.88) < 0.01

    async def test_empty_rules_list(self, async_client):
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [],
        })
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 0

    async def test_contribution_recorded(self, async_client):
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Always test edge cases", "category": "testing", "source_excerpt": "from code review"}],
        })
        pid = resp.json()["results"][0]["proposal_id"]
        contribs = await db.list_proposal_contributions(pid)
        assert len(contribs) == 1
        assert contribs[0]["contributor_name"] == "Alice"
        assert contribs[0]["original_rule_text"] == "Always test edge cases"
        assert contribs[0]["source_excerpt"] == "from code review"

    async def test_same_contributor_twice_still_merges(self, async_client):
        """Same person contributing a similar rule twice should still merge."""
        await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Always use async/await for database operations"}],
        })
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Use async/await for all database operations"}],
        })
        assert resp.json()["results"][0]["action"] == "merged"


# ============================================================
# API: GET /api/proposals/{id}/contributions
# ============================================================

class TestContributionsEndpoint:
    async def test_get_contributions(self, async_client):
        # Create via contribute endpoint
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Test rule for contributions endpoint"}],
        })
        pid = resp.json()["results"][0]["proposal_id"]

        # Add another contribution directly
        await db.add_proposal_contribution(pid, "Bob", "Similar test rule", 0.85, "", 0.72)

        resp2 = await async_client.get(f"/api/proposals/{pid}/contributions")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["proposal_id"] == pid
        assert len(data["contributions"]) == 2

    async def test_contributions_not_found(self, async_client):
        resp = await async_client.get("/api/proposals/99999/contributions")
        assert resp.status_code == 404


# ============================================================
# Proposal approval with consensus trail
# ============================================================

class TestApprovalWithConsensus:
    async def test_approve_with_contributors_creates_trail(self, async_client):
        # Create proposal with multiple contributors (strings must be >0.65 similar)
        await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Always validate input data before processing it", "category": "security", "confidence": 0.85}],
        })
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Bob",
            "rules": [{"rule_text": "Always validate input data before using it", "category": "security", "confidence": 0.80}],
        })
        result = resp.json()["results"][0]
        pid = result["proposal_id"]

        # Approve
        await async_client.put(f"/api/proposals/{pid}", json={
            "status": "approved",
            "reviewed_by": "Carol",
            "feedback": "Good consensus",
        })

        # Check that a rule was created and has a trail entry with consensus info
        rules = await db.list_rules()
        matched = [r for r in rules if "validate input data before" in r["rule_text"].lower()]
        assert len(matched) >= 1
        rule = matched[0]
        trail = await db.get_trail_for_rule(rule["id"])
        assert len(trail) >= 1
        approved_entries = [t for t in trail if t["event_type"] == "approved"]
        assert len(approved_entries) == 1
        assert "consensus" in approved_entries[0]["description"].lower()
        assert "Alice" in approved_entries[0]["description"]
        assert "Bob" in approved_entries[0]["description"]

    async def test_approve_single_contributor_no_consensus_label(self, async_client):
        await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Unique rule only Alice proposed xyz123"}],
        })
        proposals = await db.list_proposals(status="pending")
        target = [p for p in proposals if "xyz123" in p["rule_text"]]
        assert len(target) == 1
        pid = target[0]["id"]

        await async_client.put(f"/api/proposals/{pid}", json={
            "status": "approved",
            "reviewed_by": "Bob",
        })

        rules = await db.list_rules()
        matched = [r for r in rules if "xyz123" in r["rule_text"]]
        assert len(matched) == 1
        trail = await db.get_trail_for_rule(matched[0]["id"])
        approved_entries = [t for t in trail if t["event_type"] == "approved"]
        # Single contributor → no "consensus" mention
        assert "consensus" not in approved_entries[0]["description"].lower()


# ============================================================
# Client script: heuristic extraction (unit tests)
# ============================================================

class TestClientHeuristics:
    def test_extract_always_pattern(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Always use type hints in function signatures."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1
        assert rules[0]["category"] == "workflow"

    def test_extract_never_pattern(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Never commit secrets or API keys to the repository."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1
        assert rules[0]["confidence"] >= 0.7

    def test_extract_use_instead_of(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Use httpx instead of requests for async HTTP calls."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1
        assert rules[0]["category"] == "style"

    def test_extract_prefer_over(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Prefer pathlib over os.path for file path manipulation."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1

    def test_extract_avoid_pattern(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Avoid using global mutable state in module-level code."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1
        assert rules[0]["category"] == "style"

    def test_extract_dedup(self):
        from tacit_client import extract_rules_heuristic
        messages = [
            "Always use type hints in function signatures.",
            "Always use type hints in function signatures.",  # duplicate
        ]
        rules = extract_rules_heuristic(messages)
        assert len(rules) == 1

    def test_too_short_ignored(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Always test."]  # too short (< 20 chars)
        rules = extract_rules_heuristic(messages)
        assert len(rules) == 0

    def test_too_long_ignored(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Always " + "x" * 300 + " something."]  # > 300 chars
        rules = extract_rules_heuristic(messages)
        assert len(rules) == 0

    def test_no_match(self):
        from tacit_client import extract_rules_heuristic
        messages = ["The function returns a list of integers."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) == 0

    def test_ensure_pattern(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Ensure all database migrations are reversible before deploying."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1

    def test_must_pattern(self):
        from tacit_client import extract_rules_heuristic
        messages = ["Must run the full test suite before creating a pull request."]
        rules = extract_rules_heuristic(messages)
        assert len(rules) >= 1
        assert rules[0]["category"] == "architecture"


class TestClientPathEncoding:
    def test_encode_absolute_path(self):
        from tacit_client import encode_project_path
        assert encode_project_path("/Users/dev/project") == "Users-dev-project"

    def test_encode_relative_path(self):
        from tacit_client import encode_project_path
        assert encode_project_path("dev/project") == "dev-project"

    def test_encode_root(self):
        from tacit_client import encode_project_path
        assert encode_project_path("/") == ""


class TestClientGitDetection:
    def test_detect_no_git(self, tmp_path):
        from tacit_client import detect_project_hint
        result = detect_project_hint(str(tmp_path))
        assert result == ""

    def test_detect_with_git_remote(self, tmp_path):
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "remote", "add", "origin", "https://github.com/acme/widgets.git"],
            capture_output=True,
        )
        from tacit_client import detect_project_hint
        result = detect_project_hint(str(tmp_path))
        assert result == "acme/widgets"

    def test_detect_ssh_remote(self, tmp_path):
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "remote", "add", "origin", "git@github.com:acme/widgets.git"],
            capture_output=True,
        )
        from tacit_client import detect_project_hint
        result = detect_project_hint(str(tmp_path))
        assert result == "acme/widgets"


# ============================================================
# Integration: batch within /api/contribute deduplicates internally
# ============================================================

class TestContributeBatchDedup:
    async def test_batch_similar_rules_from_same_person(self, async_client):
        """Two similar rules in the same batch: first creates, second merges."""
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [
                {"rule_text": "Always use async/await for database operations", "category": "architecture"},
                {"rule_text": "Use async/await for all database calls", "category": "architecture"},
            ],
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["action"] == "created"
        assert results[1]["action"] == "merged"
        assert results[1]["proposal_id"] == results[0]["proposal_id"]

    async def test_batch_dissimilar_rules(self, async_client):
        resp = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [
                {"rule_text": "Always use type hints in Python functions"},
                {"rule_text": "Pin npm dependency versions in package.json"},
            ],
        })
        results = resp.json()["results"]
        assert results[0]["action"] == "created"
        assert results[1]["action"] == "created"
        assert results[0]["proposal_id"] != results[1]["proposal_id"]


# ============================================================
# Semantic similarity: Claude-powered matching
# ============================================================

class TestSemanticSimilarity:
    async def test_claude_similarity_fallback_no_api_key(self):
        """When ANTHROPIC_API_KEY is empty, falls back to SequenceMatcher."""
        proposals = [
            {"id": 1, "rule_text": "Always use async/await for database operations"},
        ]
        with patch("main.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = ""
            match, score = await find_semantic_match(
                "Use async/await for all database operations", proposals
            )
        assert match is not None
        assert match["id"] == 1
        assert score > 0.65

    async def test_claude_similarity_fallback_on_exception(self):
        """When Claude call raises, falls back to SequenceMatcher."""
        proposals = [
            {"id": 1, "rule_text": "Always use async/await for database operations"},
        ]
        with patch("main.settings") as mock_settings, \
             patch("main._claude_semantic_match", side_effect=Exception("API error")):
            mock_settings.ANTHROPIC_API_KEY = "test-key"
            match, score = await find_semantic_match(
                "Use async/await for all database operations", proposals
            )
        assert match is not None
        assert match["id"] == 1
        assert score > 0.65

    async def test_claude_similarity_no_match(self):
        """No match returns (None, 0.0)."""
        proposals = [
            {"id": 1, "rule_text": "Always use async/await for database operations"},
        ]
        match, score = _sequencematcher_fallback(
            "Pin all npm dependencies to exact versions", proposals
        )
        assert match is None
        assert score == 0.0

    async def test_claude_similarity_empty_proposals(self):
        """Empty proposals list returns (None, 0.0)."""
        match, score = await find_semantic_match("any rule", [])
        assert match is None
        assert score == 0.0

    async def test_semantic_merge_via_mock(self, async_client, mock_claude_similarity):
        """When Claude mock returns a match, the contribute endpoint merges."""
        # Override the autouse mock with a custom one that always matches
        proposal = {"id": 99, "rule_text": "Write tests before merging"}

        async def _always_match(rule_text, pending):
            if pending:
                return pending[0], 0.85
            return None, 0.0

        mock_claude_similarity.side_effect = _always_match

        # Create first proposal
        resp1 = await async_client.post("/api/contribute", json={
            "contributor_name": "Alice",
            "rules": [{"rule_text": "Write tests before merging"}],
        })
        assert resp1.json()["results"][0]["action"] == "created"

        # Semantically different wording should still merge via mock
        resp2 = await async_client.post("/api/contribute", json={
            "contributor_name": "Bob",
            "rules": [{"rule_text": "Add test coverage for all PRs"}],
        })
        result = resp2.json()["results"][0]
        assert result["action"] == "merged"

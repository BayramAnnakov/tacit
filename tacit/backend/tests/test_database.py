"""Tests for database CRUD operations."""

import pytest

import database as db


class TestRepos:
    async def test_create(self):
        repo = await db.create_repo("owner", "repo")
        assert repo["owner"] == "owner"
        assert repo["name"] == "repo"
        assert repo["full_name"] == "owner/repo"
        assert repo["github_url"] == "https://github.com/owner/repo"

    async def test_create_with_token(self):
        repo = await db.create_repo("owner", "repo", github_token="ghp_abc")
        assert repo["github_token"] == "ghp_abc"

    async def test_list_empty(self):
        repos = await db.list_repos()
        assert repos == []

    async def test_list_multiple(self):
        await db.create_repo("a", "first")
        await db.create_repo("b", "second")
        repos = await db.list_repos()
        assert len(repos) == 2
        names = {r["name"] for r in repos}
        assert names == {"first", "second"}

    async def test_get_found(self):
        repo = await db.create_repo("x", "y")
        fetched = await db.get_repo(repo["id"])
        assert fetched is not None
        assert fetched["full_name"] == "x/y"

    async def test_get_not_found(self):
        fetched = await db.get_repo(9999)
        assert fetched is None


class TestRules:
    async def test_insert(self):
        rule = await db.insert_rule("test rule", "testing", 0.9, "pr", "ref1")
        assert rule["rule_text"] == "test rule"
        assert rule["category"] == "testing"
        assert rule["confidence"] == 0.9
        assert rule["feedback_score"] == 0

    async def test_insert_with_repo_id(self):
        repo = await db.create_repo("o", "r")
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref", repo["id"])
        assert rule["repo_id"] == repo["id"]

    async def test_list_all(self):
        await db.insert_rule("r1", "testing", 0.9, "pr", "ref1")
        await db.insert_rule("r2", "style", 0.8, "docs", "ref2")
        rules = await db.list_rules()
        assert len(rules) == 2

    async def test_list_by_category(self):
        await db.insert_rule("r1", "testing", 0.9, "pr", "ref1")
        await db.insert_rule("r2", "style", 0.8, "docs", "ref2")
        rules = await db.list_rules(category="testing")
        assert len(rules) == 1
        assert rules[0]["category"] == "testing"

    async def test_list_by_repo_id(self):
        repo = await db.create_repo("o", "r")
        await db.insert_rule("r1", "testing", 0.9, "pr", "ref1", repo["id"])
        await db.insert_rule("r2", "style", 0.8, "docs", "ref2")
        rules = await db.list_rules(repo_id=repo["id"])
        assert len(rules) == 1

    async def test_get_found(self):
        rule = await db.insert_rule("test", "general", 0.8, "pr", "ref")
        fetched = await db.get_rule(rule["id"])
        assert fetched is not None
        assert fetched["rule_text"] == "test"

    async def test_get_not_found(self):
        fetched = await db.get_rule(9999)
        assert fetched is None

    async def test_search(self):
        await db.insert_rule("always use pytest", "testing", 0.9, "pr", "ref")
        await db.insert_rule("prefer unittest", "testing", 0.7, "pr", "ref")
        results = await db.search_rules("pytest")
        assert len(results) == 1
        assert "pytest" in results[0]["rule_text"]

    async def test_search_with_category(self):
        await db.insert_rule("use pytest", "testing", 0.9, "pr", "ref")
        await db.insert_rule("pytest configs", "style", 0.7, "pr", "ref")
        results = await db.search_rules("pytest", category="testing")
        assert len(results) == 1
        assert results[0]["category"] == "testing"

    async def test_delete(self):
        rule = await db.insert_rule("to delete", "general", 0.8, "pr", "ref")
        success = await db.delete_rule(rule["id"])
        assert success is True
        assert await db.get_rule(rule["id"]) is None

    async def test_delete_not_found(self):
        success = await db.delete_rule(9999)
        assert success is False


class TestFeedback:
    async def test_upvote(self):
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref")
        updated = await db.update_feedback_score(rule["id"], 1)
        assert updated["feedback_score"] == 1

    async def test_downvote(self):
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref")
        updated = await db.update_feedback_score(rule["id"], -1)
        assert updated["feedback_score"] == -1

    async def test_multiple_votes(self):
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref")
        await db.update_feedback_score(rule["id"], 1)
        await db.update_feedback_score(rule["id"], 1)
        updated = await db.update_feedback_score(rule["id"], -1)
        assert updated["feedback_score"] == 1


class TestSourceQuality:
    async def test_stats(self):
        await db.insert_rule("r1", "testing", 0.9, "pr", "ref1")
        await db.insert_rule("r2", "style", 0.8, "pr", "ref2")
        await db.insert_rule("r3", "testing", 0.95, "ci_fix", "ref3")
        stats = await db.get_source_quality_stats()
        assert len(stats) == 2
        source_types = {s["source_type"] for s in stats}
        assert "pr" in source_types
        assert "ci_fix" in source_types


class TestProposals:
    async def test_create(self):
        p = await db.create_proposal("rule text", "testing", 0.85, "excerpt", "Alice")
        assert p["rule_text"] == "rule text"
        assert p["status"] == "pending"

    async def test_list_all(self):
        await db.create_proposal("r1", "testing", 0.8, "", "")
        await db.create_proposal("r2", "style", 0.7, "", "")
        proposals = await db.list_proposals()
        assert len(proposals) == 2

    async def test_list_by_status(self):
        await db.create_proposal("r1", "testing", 0.8, "", "")
        p2 = await db.create_proposal("r2", "style", 0.7, "", "")
        await db.update_proposal(p2["id"], "approved")
        pending = await db.list_proposals(status="pending")
        assert len(pending) == 1

    async def test_get_found(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "")
        fetched = await db.get_proposal(p["id"])
        assert fetched is not None
        assert fetched["rule_text"] == "rule"

    async def test_get_not_found(self):
        fetched = await db.get_proposal(9999)
        assert fetched is None

    async def test_update(self):
        p = await db.create_proposal("rule", "general", 0.8, "", "")
        updated = await db.update_proposal(p["id"], "rejected", "not useful", "Bob")
        assert updated["status"] == "rejected"
        assert updated["feedback"] == "not useful"
        assert updated["reviewed_by"] == "Bob"


class TestDecisionTrail:
    async def test_add_entry(self):
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref")
        entry = await db.add_trail_entry(rule["id"], "created", "Initial extraction", "PR#1")
        assert entry["rule_id"] == rule["id"]
        assert entry["event_type"] == "created"

    async def test_get_for_rule(self):
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref")
        await db.add_trail_entry(rule["id"], "created", "First", "ref1")
        await db.add_trail_entry(rule["id"], "refined", "Second", "ref2")
        trail = await db.get_trail_for_rule(rule["id"])
        assert len(trail) == 2
        assert trail[0]["event_type"] == "created"
        assert trail[1]["event_type"] == "refined"

    async def test_get_empty(self):
        rule = await db.insert_rule("rule", "general", 0.8, "pr", "ref")
        trail = await db.get_trail_for_rule(rule["id"])
        assert trail == []


class TestExtractionRuns:
    async def test_create_run(self):
        repo = await db.create_repo("o", "r")
        run = await db.create_extraction_run(repo["id"])
        assert run["repo_id"] == repo["id"]
        assert run["status"] == "running"
        assert run["stage"] == "initializing"

    async def test_update_run(self):
        repo = await db.create_repo("o", "r")
        run = await db.create_extraction_run(repo["id"])
        updated = await db.update_extraction_run(
            run["id"], status="completed", stage="done", rules_found=5
        )
        assert updated["status"] == "completed"
        assert updated["rules_found"] == 5


class TestTeamMembers:
    async def test_create_member(self):
        member = await db.create_team_member("Alice", "🎯", "lead")
        assert member["name"] == "Alice"
        assert member["avatar_emoji"] == "🎯"
        assert member["role"] == "lead"

    async def test_create_duplicate(self):
        await db.create_team_member("Alice")
        dup = await db.create_team_member("Alice")
        assert dup["name"] == "Alice"
        members = await db.list_team_members()
        assert len(members) == 1

    async def test_list_members(self):
        await db.create_team_member("Alice")
        await db.create_team_member("Bob")
        members = await db.list_team_members()
        assert len(members) == 2

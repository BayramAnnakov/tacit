"""Tests for knowledge API endpoints (list, get, feedback, source quality)."""

import pytest

import database as db


class TestListKnowledge:
    async def test_list_empty(self, async_client):
        resp = await async_client.get("/api/knowledge")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_rules(self, async_client, seeded_rules):
        resp = await async_client.get("/api/knowledge")
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    async def test_filter_by_category(self, async_client, seeded_rules):
        resp = await async_client.get("/api/knowledge", params={"category": "testing"})
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) == 1
        assert rules[0]["category"] == "testing"

    async def test_filter_by_repo_id(self, async_client, seeded_rules, seeded_repo):
        resp = await async_client.get("/api/knowledge", params={"repo_id": seeded_repo["id"]})
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    async def test_search(self, async_client, seeded_rules):
        resp = await async_client.get("/api/knowledge", params={"q": "pytest"})
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) == 1
        assert "pytest" in rules[0]["rule_text"]


class TestGetKnowledge:
    async def test_get_with_trail(self, async_client, seeded_rules):
        rule_id = seeded_rules[0]["id"]
        await db.add_trail_entry(rule_id, "created", "test")
        resp = await async_client.get(f"/api/knowledge/{rule_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "rule" in data
        assert "decision_trail" in data
        assert len(data["decision_trail"]) == 1

    async def test_get_not_found(self, async_client):
        resp = await async_client.get("/api/knowledge/9999")
        assert resp.status_code == 404


class TestFeedback:
    async def test_upvote(self, async_client, seeded_rules):
        rule_id = seeded_rules[0]["id"]
        resp = await async_client.post(
            f"/api/knowledge/{rule_id}/feedback", json={"vote": "up"}
        )
        assert resp.status_code == 200
        assert resp.json()["feedback_score"] == 1

    async def test_downvote(self, async_client, seeded_rules):
        rule_id = seeded_rules[0]["id"]
        resp = await async_client.post(
            f"/api/knowledge/{rule_id}/feedback", json={"vote": "down"}
        )
        assert resp.status_code == 200
        assert resp.json()["feedback_score"] == -1

    async def test_nonexistent_rule(self, async_client):
        resp = await async_client.post(
            "/api/knowledge/9999/feedback", json={"vote": "up"}
        )
        assert resp.status_code == 404

    async def test_multiple_votes(self, async_client, seeded_rules):
        rule_id = seeded_rules[0]["id"]
        await async_client.post(f"/api/knowledge/{rule_id}/feedback", json={"vote": "up"})
        await async_client.post(f"/api/knowledge/{rule_id}/feedback", json={"vote": "up"})
        resp = await async_client.post(
            f"/api/knowledge/{rule_id}/feedback", json={"vote": "down"}
        )
        assert resp.status_code == 200
        assert resp.json()["feedback_score"] == 1


class TestSourceQuality:
    async def test_stats(self, async_client, seeded_rules):
        resp = await async_client.get("/api/stats/source-quality")
        assert resp.status_code == 200
        data = resp.json()
        assert "source_quality" in data
        source_types = {s["source_type"] for s in data["source_quality"]}
        assert len(source_types) >= 2

    async def test_stats_empty(self, async_client):
        resp = await async_client.get("/api/stats/source-quality")
        assert resp.status_code == 200
        assert resp.json() == {"source_quality": []}

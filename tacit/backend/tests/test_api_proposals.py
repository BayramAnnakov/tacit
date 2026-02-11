"""Tests for proposal API endpoints."""

import database as db


class TestProposalCRUD:
    async def test_create(self, async_client):
        resp = await async_client.post("/api/proposals", json={
            "rule_text": "Always add tests",
            "category": "testing",
            "confidence": 0.85,
            "source_excerpt": "Team meeting",
            "proposed_by": "Alice",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_text"] == "Always add tests"
        assert data["status"] == "pending"

    async def test_list_all(self, async_client, seeded_proposal):
        resp = await async_client.get("/api/proposals")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_list_by_status(self, async_client, seeded_proposal):
        resp = await async_client.get("/api/proposals", params={"status": "pending"})
        assert resp.status_code == 200
        proposals = resp.json()
        assert all(p["status"] == "pending" for p in proposals)


class TestProposalReview:
    async def test_approve(self, async_client, seeded_proposal):
        pid = seeded_proposal["id"]
        resp = await async_client.put(f"/api/proposals/{pid}", json={
            "status": "approved",
            "feedback": "Good rule",
            "reviewed_by": "Bob",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_approve_creates_rule(self, async_client, seeded_proposal):
        pid = seeded_proposal["id"]
        await async_client.put(f"/api/proposals/{pid}", json={
            "status": "approved",
            "reviewed_by": "Bob",
        })
        # Verify rule was created from proposal
        rules = await db.list_rules()
        rule_texts = [r["rule_text"] for r in rules]
        assert seeded_proposal["rule_text"] in rule_texts

    async def test_reject(self, async_client, seeded_proposal):
        pid = seeded_proposal["id"]
        resp = await async_client.put(f"/api/proposals/{pid}", json={
            "status": "rejected",
            "feedback": "Too vague",
            "reviewed_by": "Carol",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    async def test_invalid_status(self, async_client, seeded_proposal):
        pid = seeded_proposal["id"]
        resp = await async_client.put(f"/api/proposals/{pid}", json={
            "status": "maybe",
        })
        assert resp.status_code == 400

    async def test_not_found(self, async_client):
        resp = await async_client.put("/api/proposals/9999", json={
            "status": "approved",
        })
        assert resp.status_code == 404

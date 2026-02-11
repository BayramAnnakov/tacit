"""Tests for PR validation and post-review endpoints."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import database as db


class TestValidatePR:
    async def test_validate_no_rules(self, async_client):
        """No rules in DB → early return, agent NOT called."""
        resp = await async_client.post("/api/validate-pr", json={
            "repo": "unknown/repo",
            "pr_number": 1,
            "github_token": "tok",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["violations"] == []
        assert data["total"] == 0

    async def test_validate_with_rules_no_violations(self, async_client, seeded_rules, seeded_repo):
        """Agent returns empty array → no violations."""
        with patch("pipeline._run_agent", new_callable=AsyncMock, return_value="[]"):
            resp = await async_client.post("/api/validate-pr", json={
                "repo": "test-owner/test-repo",
                "pr_number": 1,
                "github_token": "tok",
            })
        assert resp.status_code == 200
        assert resp.json()["violations"] == []

    async def test_validate_with_violations(self, async_client, seeded_rules, seeded_repo):
        """Agent returns violations JSON."""
        violations_json = json.dumps([{
            "rule_id": 1,
            "rule_text": "Use pytest",
            "file": "test_foo.py",
            "reason": "Using unittest instead",
        }])
        with patch("pipeline._run_agent", new_callable=AsyncMock, return_value=violations_json):
            resp = await async_client.post("/api/validate-pr", json={
                "repo": "test-owner/test-repo",
                "pr_number": 1,
                "github_token": "tok",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["violations"][0]["file"] == "test_foo.py"

    async def test_validate_agent_returns_garbage(self, async_client, seeded_rules, seeded_repo):
        """Agent returns non-JSON → graceful degradation, 0 violations."""
        with patch("pipeline._run_agent", new_callable=AsyncMock, return_value="I couldn't find violations"):
            resp = await async_client.post("/api/validate-pr", json={
                "repo": "test-owner/test-repo",
                "pr_number": 1,
                "github_token": "tok",
            })
        assert resp.status_code == 200
        assert resp.json()["violations"] == []

    async def test_validate_repo_not_tracked(self, async_client, seeded_rules):
        """Repo not in DB → still runs (repo_id=None), no rules match."""
        with patch("pipeline._run_agent", new_callable=AsyncMock, return_value="[]"):
            resp = await async_client.post("/api/validate-pr", json={
                "repo": "other/repo",
                "pr_number": 1,
                "github_token": "tok",
            })
        assert resp.status_code == 200


class TestPostReview:
    async def test_no_violations(self, async_client):
        resp = await async_client.post("/api/validate-pr/post-review", json={
            "repo": "owner/repo",
            "pr_number": 1,
            "github_token": "tok",
            "violations": [],
        })
        assert resp.status_code == 200
        assert resp.json()["message"] == "No violations to post"

    async def test_with_violations(self, async_client, mock_httpx_client):
        MockResponse = mock_httpx_client._MockResponse
        mock_client = mock_httpx_client._mock_client
        mock_client.post.return_value = MockResponse(
            status_code=200,
            json_data={"id": 123, "html_url": "https://github.com/o/r/pull/1#review-123"},
        )

        resp = await async_client.post("/api/validate-pr/post-review", json={
            "repo": "owner/repo",
            "pr_number": 1,
            "github_token": "tok",
            "violations": [{"file": "a.py", "reason": "bad", "rule_text": "rule"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_id"] == 123

    async def test_github_error(self, async_client, mock_httpx_client):
        MockResponse = mock_httpx_client._MockResponse
        mock_client = mock_httpx_client._mock_client
        mock_client.post.return_value = MockResponse(status_code=500)

        resp = await async_client.post("/api/validate-pr/post-review", json={
            "repo": "owner/repo",
            "pr_number": 1,
            "github_token": "tok",
            "violations": [{"file": "a.py", "reason": "bad", "rule_text": "rule"}],
        })
        assert resp.status_code == 502

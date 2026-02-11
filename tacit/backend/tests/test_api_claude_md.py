"""Tests for CLAUDE.md generation, diff, and PR creation endpoints."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import database as db


class TestGenerateClaudeMD:
    async def test_generate_no_rules(self, async_client, seeded_repo, mock_run_agent):
        mock_run_agent.return_value = ""
        resp = await async_client.get(f"/api/claude-md/{seeded_repo['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "No knowledge rules" in data["content"]

    async def test_generate_with_rules_fallback(self, async_client, seeded_rules, seeded_repo, mock_run_agent):
        """Agent returns empty → fallback builds from DB rules."""
        mock_run_agent.return_value = ""
        resp = await async_client.get(f"/api/claude-md/{seeded_repo['id']}")
        assert resp.status_code == 200
        content = resp.json()["content"]
        assert "# CLAUDE.md" in content
        assert "pytest" in content.lower() or "snake_case" in content.lower()

    async def test_generate_agent_success(self, async_client, seeded_repo, mock_run_agent):
        mock_run_agent.return_value = "# CLAUDE.md\n\n## Testing\n- Use pytest\n"
        resp = await async_client.get(f"/api/claude-md/{seeded_repo['id']}")
        assert resp.status_code == 200
        assert "Use pytest" in resp.json()["content"]

    async def test_generate_repo_not_found(self, async_client):
        resp = await async_client.get("/api/claude-md/9999")
        assert resp.status_code == 404


class TestDiff:
    async def test_diff_both_exist(self, async_client, seeded_rules, seeded_repo, mock_run_agent, mock_httpx_client):
        MockResponse = mock_httpx_client._MockResponse
        mock_client = mock_httpx_client._mock_client
        mock_client.get.return_value = MockResponse(
            status_code=200, text="# Old CLAUDE.md\n- old rule\n"
        )
        mock_run_agent.return_value = ""

        resp = await async_client.get(f"/api/claude-md/{seeded_repo['id']}/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert "existing" in data
        assert "generated" in data
        assert "diff_lines" in data
        assert data["existing"] == "# Old CLAUDE.md\n- old rule\n"

    async def test_diff_no_existing(self, async_client, seeded_rules, seeded_repo, mock_run_agent, mock_httpx_client):
        MockResponse = mock_httpx_client._MockResponse
        mock_client = mock_httpx_client._mock_client
        mock_client.get.return_value = MockResponse(status_code=404)
        mock_run_agent.return_value = ""

        resp = await async_client.get(f"/api/claude-md/{seeded_repo['id']}/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["existing"] == ""

    async def test_diff_repo_not_found(self, async_client):
        resp = await async_client.get("/api/claude-md/9999/diff")
        assert resp.status_code == 404


class TestCreatePR:
    async def test_create_pr_success(self, async_client, seeded_repo, mock_httpx_client):
        MockResponse = mock_httpx_client._MockResponse
        mock_client = mock_httpx_client._mock_client

        # Store the repo with a token
        await db.create_repo("pr-owner", "pr-repo", github_token="ghp_test")
        repos = await db.list_repos()
        repo = [r for r in repos if r["name"] == "pr-repo"][0]

        # Mock the 6 sequential GitHub API calls
        mock_client.get.side_effect = [
            # 1. Get repo info (default branch)
            MockResponse(status_code=200, json_data={"default_branch": "main"}),
            # 2. Get ref SHA
            MockResponse(status_code=200, json_data={"object": {"sha": "abc123"}}),
            # 4. Check if CLAUDE.md exists
            MockResponse(status_code=404),
        ]
        mock_client.post.side_effect = [
            # 3. Create branch ref
            MockResponse(status_code=201),
            # 6. Create PR
            MockResponse(status_code=201, json_data={
                "html_url": "https://github.com/pr-owner/pr-repo/pull/1",
                "number": 1,
            }),
        ]
        mock_client.put.return_value = MockResponse(status_code=201)  # 5. Put file

        resp = await async_client.post(f"/api/claude-md/{repo['id']}/create-pr", json={
            "content": "# CLAUDE.md\ntest content",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "pr_url" in data
        assert data["pr_number"] == 1

    async def test_create_pr_no_token(self, async_client, seeded_repo):
        """Repo has no token and no GITHUB_TOKEN in settings."""
        from config import settings
        with patch.object(settings, "GITHUB_TOKEN", ""):
            resp = await async_client.post(f"/api/claude-md/{seeded_repo['id']}/create-pr", json={
                "content": "test",
            })
        assert resp.status_code == 400

    async def test_create_pr_repo_not_found(self, async_client):
        resp = await async_client.post("/api/claude-md/9999/create-pr", json={
            "content": "test",
        })
        assert resp.status_code == 404

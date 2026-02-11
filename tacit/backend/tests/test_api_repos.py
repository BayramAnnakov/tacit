"""Tests for repository CRUD and health endpoints."""


class TestRepos:
    async def test_connect_repo(self, async_client):
        resp = await async_client.post("/api/repos", json={
            "owner": "acme",
            "name": "widgets",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "acme/widgets"

    async def test_connect_with_token(self, async_client):
        resp = await async_client.post("/api/repos", json={
            "owner": "acme",
            "name": "widgets",
            "github_token": "ghp_abc",
        })
        assert resp.status_code == 200
        assert resp.json()["github_token"] == "ghp_abc"

    async def test_list_empty(self, async_client):
        resp = await async_client.get("/api/repos")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_data(self, async_client, seeded_repo):
        resp = await async_client.get("/api/repos")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestHealth:
    async def test_health(self, async_client):
        resp = await async_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

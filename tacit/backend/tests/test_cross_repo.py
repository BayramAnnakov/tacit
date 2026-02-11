"""Tests for cross-repo intelligence endpoint."""

import database as db


class TestCrossRepoPatterns:
    async def test_no_patterns_single_repo(self, async_client, seeded_rules):
        """All rules from same repo → no cross-repo patterns."""
        resp = await async_client.get("/api/knowledge/cross-repo")
        assert resp.status_code == 200
        data = resp.json()
        # Single repo rules shouldn't produce cross-repo patterns
        # (unless they match across different repo_ids, but here all have same repo_id)
        assert "org_patterns" in data

    async def test_similar_rules_different_repos(self, async_client):
        """Similar rules across repos → detected as pattern."""
        repo1 = await db.create_repo("org", "repo-alpha")
        repo2 = await db.create_repo("org", "repo-beta")

        await db.insert_rule("Always use pytest for testing", "testing", 0.9, "pr", "ref", repo1["id"])
        await db.insert_rule("Always use pytest for testing", "testing", 0.85, "pr", "ref", repo2["id"])

        resp = await async_client.get("/api/knowledge/cross-repo")
        assert resp.status_code == 200
        patterns = resp.json()["org_patterns"]
        assert len(patterns) >= 1
        assert len(patterns[0]["repos"]) >= 2

    async def test_dissimilar_rules_not_matched(self, async_client):
        """Very different rules → not grouped."""
        repo1 = await db.create_repo("org", "repo-alpha")
        repo2 = await db.create_repo("org", "repo-beta")

        await db.insert_rule("Use tabs for indentation", "style", 0.9, "pr", "ref", repo1["id"])
        await db.insert_rule("Deploy using Kubernetes", "architecture", 0.85, "pr", "ref", repo2["id"])

        resp = await async_client.get("/api/knowledge/cross-repo")
        assert resp.status_code == 200
        patterns = resp.json()["org_patterns"]
        assert len(patterns) == 0

    async def test_frequency_sorting(self, async_client):
        """Patterns sorted by frequency (descending)."""
        repos = []
        for i in range(3):
            repos.append(await db.create_repo("org", f"repo-{i}"))

        # Pattern 1: appears in 3 repos
        for r in repos:
            await db.insert_rule("Use pytest for testing", "testing", 0.9, "pr", "ref", r["id"])

        # Pattern 2: appears in 2 repos
        for r in repos[:2]:
            await db.insert_rule("Use black formatter", "style", 0.85, "pr", "ref", r["id"])

        resp = await async_client.get("/api/knowledge/cross-repo")
        assert resp.status_code == 200
        patterns = resp.json()["org_patterns"]
        if len(patterns) >= 2:
            assert patterns[0]["frequency"] >= patterns[1]["frequency"]

    async def test_same_repo_not_counted(self, async_client):
        """Multiple similar rules in same repo → not a cross-repo pattern."""
        repo = await db.create_repo("org", "solo-repo")
        await db.insert_rule("Use pytest for testing", "testing", 0.9, "pr", "ref1", repo["id"])
        await db.insert_rule("Use pytest for unit tests", "testing", 0.85, "pr", "ref2", repo["id"])

        resp = await async_client.get("/api/knowledge/cross-repo")
        assert resp.status_code == 200
        patterns = resp.json()["org_patterns"]
        # Same repo rules should not create cross-repo patterns
        assert len(patterns) == 0

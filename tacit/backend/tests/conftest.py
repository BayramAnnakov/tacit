"""Shared fixtures for Tacit backend tests."""

import os
import sys
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
async def test_db(tmp_path):
    """Patch DB_PATH to a per-test temp file, init schema, clean after."""
    import database as db_module

    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path

    await db_module.init_db()
    yield

    db_module.DB_PATH = original


@pytest_asyncio.fixture
async def async_client():
    """HTTPX async client wired to the FastAPI app without invoking lifespan."""
    import httpx
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def seeded_repo():
    """Create a test repository and return its dict."""
    import database as db

    repo = await db.create_repo("test-owner", "test-repo")
    return repo


@pytest_asyncio.fixture
async def seeded_rules(seeded_repo):
    """Insert 5 rules across different categories/source types."""
    import database as db

    repo_id = seeded_repo["id"]
    rules = []
    data = [
        ("Use pytest for all tests", "testing", 0.9, "pr", "PR#1", repo_id),
        ("Never commit .env files", "security", 0.95, "ci_fix", "CI#42", repo_id),
        ("Use snake_case for functions", "style", 0.85, "docs", "README", repo_id),
        ("Run linter before push", "workflow", 0.8, "structure", "hooks/pre-push", repo_id),
        ("Use async/await for IO", "architecture", 0.7, "config", ".eslintrc", repo_id),
    ]
    for rule_text, category, confidence, source_type, source_ref, rid in data:
        rule = await db.insert_rule(rule_text, category, confidence, source_type, source_ref, rid)
        rules.append(rule)
    return rules


@pytest_asyncio.fixture
async def seeded_proposal():
    """Create a pending proposal."""
    import database as db

    return await db.create_proposal(
        rule_text="Always add type hints",
        category="style",
        confidence=0.85,
        source_excerpt="Team discussion about type safety",
        proposed_by="Alice",
    )


@pytest.fixture
def mock_run_agent():
    """Patch pipeline._run_agent to prevent Claude API calls."""
    with patch("pipeline._run_agent", new_callable=AsyncMock) as mock:
        mock.return_value = "[]"
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Patch httpx.AsyncClient for GitHub API mocking."""

    class MockResponse:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self._json = json_data or {}
            self.text = text

        def json(self):
            return self._json

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=MockResponse())
    mock_client.post = AsyncMock(return_value=MockResponse())
    mock_client.put = AsyncMock(return_value=MockResponse())

    with patch("httpx.AsyncClient", return_value=mock_client) as patcher:
        patcher._mock_client = mock_client
        patcher._MockResponse = MockResponse
        yield patcher

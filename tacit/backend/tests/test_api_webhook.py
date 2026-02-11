"""Tests for GitHub webhook endpoint."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch


def _make_webhook_payload(action="closed", merged=True, repo_full_name="test-owner/test-repo", pr_number=42):
    return {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "merged": merged,
        },
        "repository": {
            "full_name": repo_full_name,
        },
    }


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


class TestWebhookBasic:
    async def test_non_merged_pr_ignored(self, async_client, seeded_repo):
        payload = _make_webhook_payload(action="opened")
        resp = await async_client.post("/api/webhook/github", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ignored"] is True

    async def test_closed_not_merged_ignored(self, async_client, seeded_repo):
        payload = _make_webhook_payload(action="closed", merged=False)
        resp = await async_client.post("/api/webhook/github", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ignored"] is True

    async def test_untracked_repo_ignored(self, async_client):
        payload = _make_webhook_payload(repo_full_name="unknown/repo")
        resp = await async_client.post("/api/webhook/github", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ignored"] is True
        assert "not tracked" in resp.json()["reason"]

    async def test_merged_pr_accepted(self, async_client, seeded_repo):
        payload = _make_webhook_payload()
        with patch("main._webhook_extraction_background", new_callable=AsyncMock):
            resp = await async_client.post("/api/webhook/github", json=payload)
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True
        assert resp.json()["pr_number"] == 42


class TestWebhookHMAC:
    async def test_hmac_valid(self, async_client, seeded_repo):
        from config import settings

        secret = "test-secret-123"
        payload = _make_webhook_payload()
        payload_bytes = json.dumps(payload).encode()
        signature = _sign_payload(payload_bytes, secret)

        original = settings.WEBHOOK_SECRET
        settings.WEBHOOK_SECRET = secret
        try:
            with patch("main._webhook_extraction_background", new_callable=AsyncMock):
                resp = await async_client.post(
                    "/api/webhook/github",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": signature,
                    },
                )
        finally:
            settings.WEBHOOK_SECRET = original
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

    async def test_hmac_invalid(self, async_client, seeded_repo):
        from config import settings

        secret = "test-secret-123"
        payload = _make_webhook_payload()
        payload_bytes = json.dumps(payload).encode()

        original = settings.WEBHOOK_SECRET
        settings.WEBHOOK_SECRET = secret
        try:
            resp = await async_client.post(
                "/api/webhook/github",
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )
        finally:
            settings.WEBHOOK_SECRET = original
        assert resp.status_code == 403

    async def test_hmac_missing_when_required(self, async_client, seeded_repo):
        from config import settings

        secret = "test-secret-123"
        payload = _make_webhook_payload()
        payload_bytes = json.dumps(payload).encode()

        original = settings.WEBHOOK_SECRET
        settings.WEBHOOK_SECRET = secret
        try:
            resp = await async_client.post(
                "/api/webhook/github",
                content=payload_bytes,
                headers={"Content-Type": "application/json"},
            )
        finally:
            settings.WEBHOOK_SECRET = original
        assert resp.status_code == 403

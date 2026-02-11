"""Tests for pipeline orchestration functions."""

import json
from unittest.mock import AsyncMock, patch

import database as db
from pipeline import _parse_pr_numbers, generate_claude_md, run_single_pr_extraction


class TestParsePRNumbers:
    def test_json_array(self):
        result = '[{"pr_number": 1}, {"pr_number": 2}, {"pr_number": 3}]'
        assert _parse_pr_numbers(result) == [1, 2, 3]

    def test_json_in_multiline(self):
        result = 'Here are the PRs:\n[{"pr_number": 10}, {"pr_number": 20}]\nDone.'
        assert _parse_pr_numbers(result) == [10, 20]

    def test_invalid_json(self):
        result = "I found some interesting PRs but couldn't format them"
        numbers = _parse_pr_numbers(result)
        assert numbers == [1, 2, 3, 4, 5]  # fallback

    def test_empty_array(self):
        result = "[]"
        assert _parse_pr_numbers(result) == []


class TestGenerateClaudeMD:
    async def test_fallback_sections(self, seeded_rules, seeded_repo, mock_run_agent):
        """Agent returns empty → fallback produces section-organized markdown."""
        mock_run_agent.return_value = ""
        content = await generate_claude_md(seeded_repo["id"])
        assert "# CLAUDE.md" in content
        # Should have at least some sections
        assert "##" in content

    async def test_fallback_empty(self, seeded_repo, mock_run_agent):
        """No rules at all → placeholder message."""
        mock_run_agent.return_value = ""
        content = await generate_claude_md(seeded_repo["id"])
        assert "No knowledge rules" in content

    async def test_agent_success(self, seeded_repo, mock_run_agent):
        """Agent returns content → use it directly."""
        mock_run_agent.return_value = "# CLAUDE.md\n\n## Testing\n- Use pytest\n"
        content = await generate_claude_md(seeded_repo["id"])
        assert "Use pytest" in content


class TestRunSinglePRExtraction:
    async def test_repo_not_found(self, mock_run_agent):
        """Repo not in DB → returns 0."""
        count = await run_single_pr_extraction("unknown/repo", 1, "tok")
        assert count == 0

    async def test_creates_proposals(self, seeded_repo):
        """Extracts rules and creates proposals from new rules."""
        call_count = 0

        async def mock_agent(name, prompt, repo_id=None):
            nonlocal call_count
            call_count += 1
            if name == "thread-analyzer":
                # Simulate the agent storing a rule via DB
                await db.insert_rule(
                    "New rule from PR",
                    "testing",
                    0.85,
                    "pr",
                    "PR#42",
                    seeded_repo["id"],
                )
            return "done"

        with patch("pipeline._run_agent", side_effect=mock_agent):
            count = await run_single_pr_extraction(
                "test-owner/test-repo", 42, "tok"
            )

        # Should have created proposals for new rules
        proposals = await db.list_proposals()
        assert len(proposals) >= 1
        assert any("New rule from PR" in p["rule_text"] for p in proposals)

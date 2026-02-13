---
description: Critical anti-patterns and prohibitions -- always loaded
---

- NEVER modify `claude_agent_sdk` imports or internals -- they come from the SDK package
- NEVER hardcode GitHub tokens -- always read from settings/env (`settings.GITHUB_TOKEN` or `.env`)
- NEVER use `pip install` directly -- use `venv` and `pip install -r requirements.txt`
- NEVER commit `tacit.db` -- it is auto-generated on startup with schema + seed data
- NEVER remove or truncate session transcripts in `~/.claude/projects/` -- they are the raw data source for session mining
- NEVER create an agent without a matching prompt file in `tacit/backend/prompts/`
- NEVER skip `await db.close()` in database functions -- every `get_db()` call must have a matching close in a `finally` block
- NEVER allow integration tests to make actual network requests to external services -- use mock gateways
- NEVER store secrets (API keys, tokens) in source code or commit them to git

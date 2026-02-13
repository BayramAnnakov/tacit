---
description: Git, issue tracking, and development workflow
---

- Use Beads (`bd`) for issue tracking: `bd ready`, `bd create "..."`, `bd close <id>`, `bd sync`
- Activate venv before running Python: `cd tacit/backend && source venv/bin/activate`
- Delete `tacit/backend/tacit.db` and restart to reset database (auto-recreates with schema + seed data)
- Push to remote when ending a work session -- work is NOT complete until `git push` succeeds
- Requires `.env` in `tacit/backend/` with `ANTHROPIC_API_KEY` and `GITHUB_TOKEN`
- Optional: set `WEBHOOK_SECRET` in `.env` for GitHub webhook HMAC verification
- Backend runs at `http://127.0.0.1:8000` by default
- WebSocket at `/ws` for live extraction event streaming

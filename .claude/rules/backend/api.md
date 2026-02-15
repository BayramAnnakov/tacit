---
description: FastAPI endpoints, WebSocket, webhook handling
paths:
  - "tacit/backend/main.py"
---

- FastAPI app with CORS (allow all origins), WebSocket for live extraction events
- Pydantic request models defined inline in `main.py`
- Webhook handler uses `incremental_extract()` for single-PR learning from merged PRs
- PR review posting includes provenance (rule origin story) in comments
- Health endpoint returns system-wide status: hook installation, rule counts, agent count

### Endpoint groups
- **Repos**: `POST/GET /api/repos`
- **Extraction**: `POST /api/extract/{repo_id}`, `POST /api/local-extract`
- **Knowledge**: `GET /api/knowledge`, `GET /api/knowledge/{id}`, `POST /api/knowledge/{id}/feedback`, `GET /api/knowledge/cross-repo`, `GET /api/stats/source-quality`
- **Proposals**: `POST/GET /api/proposals`, `PUT /api/proposals/{id}`, `GET /api/proposals/{id}/contributions`
- **Contributions**: `POST /api/contribute` (federated contribution with Claude-powered semantic dedup)
- **CLAUDE.md**: `GET /api/claude-md/{repo_id}`, `GET /api/claude-md/{repo_id}/diff`, `POST /api/claude-md/{repo_id}/create-pr`
- **Modular rules**: `GET /api/claude-rules/{repo_id}`
- **Metrics**: `GET/POST /api/metrics/{repo_id}`, `POST /api/metrics/{repo_id}/collect`
- **PR validation**: `POST /api/validate-pr`, `POST /api/validate-pr/post-review`
- **Hooks**: `POST /api/hooks/capture`, `GET /api/hooks/config`, `GET /api/hooks/status`, `POST /api/hooks/install`
- **Sessions**: `POST /api/mine-sessions`, `GET /api/sessions`
- **Database analysis**: `POST /api/analyze-db` (schema introspection for domain knowledge)
- **Onboarding**: `POST /api/onboarding/generate`
- **Webhook**: `POST /api/webhook/github`
- **Health**: `GET /api/health`

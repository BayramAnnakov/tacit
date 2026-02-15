---
description: Agent system -- definitions, prompts, and model assignments
paths:
  - "tacit/backend/agents.py"
  - "tacit/backend/prompts/**"
---

- 16 agents defined via `AgentDefinition` dataclass in `get_agent_definitions()`
- Each agent requires: prompt file in `prompts/<name>.md`, model (`sonnet` or `opus`), tools list
- To add an agent: create prompt file, add `AgentDefinition` in `agents.py`, wire into `pipeline.py`
- Agent tool names must match entries in `_RAW_TOOL_NAMES` in `tools.py`

### Agent categories

**Extraction** (Phase 1-2):
- `pr-scanner` (sonnet), `thread-analyzer` (opus), `structural-analyzer` (sonnet)
- `docs-analyzer` (sonnet), `ci-failure-miner` (opus), `code-analyzer` (sonnet)
- `anti-pattern-miner` (opus), `domain-analyzer` (sonnet)

**Database analysis**:
- `db-schema-analyzer` (opus) -- extracts domain knowledge from database schemas

**Synthesis** (Phase 4):
- `synthesizer` (opus), `generator` (opus), `modular-generator` (opus)

**Analysis/Utility**:
- `outcome-analyzer` (sonnet), `session-analyzer` (sonnet)
- `local-extractor` (sonnet), `pr-validator` (opus)

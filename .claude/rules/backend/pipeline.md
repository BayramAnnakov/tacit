---
description: Extraction pipeline orchestrator -- phases, incremental extraction, modular generation
paths:
  - "tacit/backend/pipeline.py"
---

- 4-phase extraction in `run_extraction()`:
  - Phase 1: 5 parallel analyzers (structural, docs, CI, code, anti-pattern)
  - Phase 2: PR scanning + thread analysis (3 concurrent via `asyncio.Semaphore`)
  - Phase 3: Await Phase 1 parallel tasks
  - Phase 4: Synthesis (dedup, boost, remove generic rules) + post-synthesis programmatic filter (28 known generic patterns)
- All extraction functions are async generators yielding `ExtractionEvent`
- `incremental_extract()` for webhook-driven single-PR extraction
  - Auto-approves rules at confidence >= 0.85
  - Creates proposals for lower-confidence rules
- `generate_modular_rules()` produces `.claude/rules/` directory structure from knowledge base
- `collect_outcome_metrics()` gathers PR/CI data via outcome-analyzer agent
- `mine_session()` / `mine_all_sessions()` for Claude Code transcript mining
  - Scans `~/.claude/projects/` for JSONL transcripts
  - Tracks processed files in `mined_sessions` table to avoid re-mining
- Agents are run via `_run_agent()` which creates `ClaudeSDKClient` with `ClaudeAgentOptions`

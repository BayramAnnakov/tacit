---
description: SQLite database schema, CRUD operations, and migrations
paths:
  - "tacit/backend/database.py"
---

- SQLite via `aiosqlite` with WAL mode and foreign keys enabled
- Schema defined in `SCHEMA` constant, idempotent ALTER migrations in `init_db()`
- All CRUD functions are async, open/close db connection per call via `get_db()` + `finally: await db.close()`
- DB path configured via `settings.DB_PATH` (from `config.py`)

### Key tables
- `repositories` -- connected GitHub repos with tokens
- `knowledge_rules` -- extracted rules with `provenance_url`, `provenance_summary`, `applicable_paths`, `feedback_score`
- `proposals` -- pending/approved/rejected rule proposals with `contributor_count`
- `proposal_contributions` -- federated contribution tracking per proposal
- `extraction_runs` -- extraction run status and progress
- `decision_trail` -- audit log of rule lifecycle events
- `mined_sessions` -- tracks which transcripts have been mined (unique on `path`)
- `outcome_metrics` -- weekly PR/CI metrics per repo (unique on `repo_id, week_start`)

### Source types
`pr`, `conversation`, `structure`, `docs`, `ci_fix`, `config`, `anti_pattern`

### Authority hierarchy (when rules conflict)
`ci_fix`/`anti_pattern` > `structure`/`docs`/`config` > `pr` > `conversation`

"""SQLite database schema and CRUD operations using aiosqlite."""

import aiosqlite
from datetime import datetime, timezone

from config import settings

DB_PATH = settings.DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    github_url TEXT NOT NULL DEFAULT '',
    github_token TEXT NOT NULL DEFAULT '',
    connected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    avatar_emoji TEXT NOT NULL DEFAULT '👤',
    role TEXT NOT NULL DEFAULT 'developer'
);

CREATE TABLE IF NOT EXISTS knowledge_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    confidence REAL NOT NULL DEFAULT 0.8,
    source_type TEXT NOT NULL DEFAULT 'pr',
    source_ref TEXT NOT NULL DEFAULT '',
    repo_id INTEGER REFERENCES repositories(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    feedback_score INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    confidence REAL NOT NULL DEFAULT 0.8,
    source_excerpt TEXT NOT NULL DEFAULT '',
    proposed_by TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    feedback TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repositories(id),
    status TEXT NOT NULL DEFAULT 'running',
    stage TEXT NOT NULL DEFAULT 'initializing',
    rules_found INTEGER NOT NULL DEFAULT 0,
    prs_analyzed INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS decision_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES knowledge_rules(id),
    event_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_ref TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS proposal_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id),
    contributor_name TEXT NOT NULL,
    original_rule_text TEXT NOT NULL,
    original_confidence REAL NOT NULL DEFAULT 0.8,
    source_excerpt TEXT NOT NULL DEFAULT '',
    similarity_score REAL NOT NULL DEFAULT 1.0,
    contributed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mined_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    project_path TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    rules_found INTEGER NOT NULL DEFAULT 0,
    last_mined_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outcome_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repositories(id),
    week_start TEXT NOT NULL,
    pr_revision_rounds REAL NOT NULL DEFAULT 0,
    ci_failure_rate REAL NOT NULL DEFAULT 0,
    review_comment_density REAL NOT NULL DEFAULT 0,
    time_to_merge_hours REAL NOT NULL DEFAULT 0,
    first_timer_time_to_merge_hours REAL NOT NULL DEFAULT 0,
    rules_deployed INTEGER NOT NULL DEFAULT 0,
    measured_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(repo_id, week_start)
);
"""


async def get_db() -> aiosqlite.Connection:
    """Open a database connection with row factory enabled."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """Initialize database schema."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
        # Idempotent ALTER migrations
        for alter in [
            "ALTER TABLE proposals ADD COLUMN contributor_count INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE proposals ADD COLUMN repo_id INTEGER REFERENCES repositories(id)",
            # Improvement 4: Provenance tracking
            "ALTER TABLE knowledge_rules ADD COLUMN provenance_url TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE knowledge_rules ADD COLUMN provenance_summary TEXT NOT NULL DEFAULT ''",
            # Improvement 5: Path-scoped rules
            "ALTER TABLE knowledge_rules ADD COLUMN applicable_paths TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                await db.execute(alter)
                await db.commit()
            except Exception:
                pass  # Column already exists
    finally:
        await db.close()


# --------------- Repositories ---------------

async def create_repo(owner: str, name: str, github_token: str = "") -> dict:
    full_name = f"{owner}/{name}"
    github_url = f"https://github.com/{full_name}"
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO repositories (owner, name, full_name, github_url, github_token) VALUES (?, ?, ?, ?, ?)",
            (owner, name, full_name, github_url, github_token),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM repositories WHERE id = ?", (cursor.lastrowid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def list_repos() -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute("SELECT * FROM repositories ORDER BY connected_at DESC")).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_repo(repo_id: int) -> dict | None:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# --------------- Team Members ---------------

async def create_team_member(name: str, avatar_emoji: str = "👤", role: str = "developer") -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO team_members (name, avatar_emoji, role) VALUES (?, ?, ?)",
            (name, avatar_emoji, role),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM team_members WHERE name = ?", (name,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def list_team_members() -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute("SELECT * FROM team_members ORDER BY id")).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --------------- Knowledge Rules ---------------

async def insert_rule(rule_text: str, category: str, confidence: float,
                      source_type: str, source_ref: str, repo_id: int | None = None,
                      provenance_url: str = "", provenance_summary: str = "",
                      applicable_paths: str = "") -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO knowledge_rules
               (rule_text, category, confidence, source_type, source_ref, repo_id,
                provenance_url, provenance_summary, applicable_paths)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule_text, category, confidence, source_type, source_ref, repo_id,
             provenance_url, provenance_summary, applicable_paths),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM knowledge_rules WHERE id = ?", (cursor.lastrowid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def list_rules(category: str | None = None, repo_id: int | None = None) -> list[dict]:
    db = await get_db()
    try:
        query = "SELECT * FROM knowledge_rules WHERE 1=1"
        params: list = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if repo_id is not None:
            query += " AND repo_id = ?"
            params.append(repo_id)
        query += " ORDER BY confidence DESC, created_at DESC"
        rows = await (await db.execute(query, params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_rule(rule_id: int) -> dict | None:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT * FROM knowledge_rules WHERE id = ?", (rule_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def search_rules(query_text: str, category: str | None = None, repo_id: int | None = None) -> list[dict]:
    db = await get_db()
    try:
        sql = "SELECT * FROM knowledge_rules WHERE rule_text LIKE ?"
        params: list = [f"%{query_text}%"]
        if category:
            sql += " AND category = ?"
            params.append(category)
        if repo_id is not None:
            sql += " AND repo_id = ?"
            params.append(repo_id)
        sql += " ORDER BY confidence DESC"
        rows = await (await db.execute(sql, params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def delete_rule(rule_id: int) -> bool:
    db = await get_db()
    try:
        # Delete associated decision trail entries first
        await db.execute("DELETE FROM decision_trail WHERE rule_id = ?", (rule_id,))
        cursor = await db.execute("DELETE FROM knowledge_rules WHERE id = ?", (rule_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def update_feedback_score(rule_id: int, delta: int) -> dict | None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE knowledge_rules SET feedback_score = feedback_score + ? WHERE id = ?",
            (delta, rule_id),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM knowledge_rules WHERE id = ?", (rule_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_source_quality_stats() -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute(
            """SELECT source_type,
                      COUNT(*) as count,
                      ROUND(AVG(confidence), 2) as avg_confidence,
                      ROUND(AVG(feedback_score), 2) as avg_feedback
               FROM knowledge_rules
               GROUP BY source_type
               ORDER BY avg_confidence DESC"""
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --------------- Proposals ---------------

async def create_proposal(rule_text: str, category: str, confidence: float,
                          source_excerpt: str, proposed_by: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO proposals (rule_text, category, confidence, source_excerpt, proposed_by)
               VALUES (?, ?, ?, ?, ?)""",
            (rule_text, category, confidence, source_excerpt, proposed_by),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM proposals WHERE id = ?", (cursor.lastrowid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def list_proposals(status: str | None = None) -> list[dict]:
    db = await get_db()
    try:
        if status:
            rows = await (await db.execute(
                "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC", (status,)
            )).fetchall()
        else:
            rows = await (await db.execute("SELECT * FROM proposals ORDER BY created_at DESC")).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_proposal(proposal_id: int) -> dict | None:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_proposal(proposal_id: int, status: str, feedback: str = "", reviewed_by: str = "") -> dict | None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE proposals SET status = ?, feedback = ?, reviewed_by = ? WHERE id = ?",
            (status, feedback, reviewed_by, proposal_id),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# --------------- Extraction Runs ---------------

async def create_extraction_run(repo_id: int) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO extraction_runs (repo_id) VALUES (?)", (repo_id,)
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM extraction_runs WHERE id = ?", (cursor.lastrowid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def update_extraction_run(run_id: int, **kwargs: object) -> dict | None:
    db = await get_db()
    try:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values())
        vals.append(run_id)
        await db.execute(f"UPDATE extraction_runs SET {sets} WHERE id = ?", vals)
        await db.commit()
        row = await (await db.execute("SELECT * FROM extraction_runs WHERE id = ?", (run_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# --------------- Decision Trail ---------------

async def add_trail_entry(rule_id: int, event_type: str, description: str = "", source_ref: str = "") -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO decision_trail (rule_id, event_type, description, source_ref)
               VALUES (?, ?, ?, ?)""",
            (rule_id, event_type, description, source_ref),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM decision_trail WHERE id = ?", (cursor.lastrowid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_trail_for_rule(rule_id: int) -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute(
            "SELECT * FROM decision_trail WHERE rule_id = ? ORDER BY timestamp ASC", (rule_id,)
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --------------- Proposal Contributions ---------------

async def add_proposal_contribution(
    proposal_id: int, contributor_name: str, original_rule_text: str,
    original_confidence: float = 0.8, source_excerpt: str = "", similarity_score: float = 1.0,
) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO proposal_contributions
               (proposal_id, contributor_name, original_rule_text, original_confidence, source_excerpt, similarity_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (proposal_id, contributor_name, original_rule_text, original_confidence, source_excerpt, similarity_score),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM proposal_contributions WHERE id = ?", (cursor.lastrowid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def list_proposal_contributions(proposal_id: int) -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute(
            "SELECT * FROM proposal_contributions WHERE proposal_id = ? ORDER BY contributed_at ASC",
            (proposal_id,),
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_contribution_count(proposal_id: int) -> int:
    db = await get_db()
    try:
        row = await (await db.execute(
            "SELECT COUNT(DISTINCT contributor_name) as cnt FROM proposal_contributions WHERE proposal_id = ?",
            (proposal_id,),
        )).fetchone()
        return row["cnt"] if row else 0
    finally:
        await db.close()


async def update_proposal_confidence(proposal_id: int, confidence: float, contributor_count: int) -> dict | None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE proposals SET confidence = ?, contributor_count = ? WHERE id = ?",
            (confidence, contributor_count, proposal_id),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_proposal_repo_id(proposal_id: int, repo_id: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE proposals SET repo_id = ? WHERE id = ?",
            (repo_id, proposal_id),
        )
        await db.commit()
    finally:
        await db.close()


# --------------- Mined Sessions ---------------

async def upsert_mined_session(path: str, project_path: str, message_count: int, rules_found: int) -> dict:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO mined_sessions (path, project_path, message_count, rules_found, last_mined_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(path) DO UPDATE SET
                 message_count = excluded.message_count,
                 rules_found = excluded.rules_found,
                 last_mined_at = datetime('now')""",
            (path, project_path, message_count, rules_found),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM mined_sessions WHERE path = ?", (path,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_mined_session(path: str) -> dict | None:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT * FROM mined_sessions WHERE path = ?", (path,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_mined_sessions() -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute(
            "SELECT * FROM mined_sessions ORDER BY last_mined_at DESC"
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def find_similar_pending_proposals(rule_text: str) -> list[dict]:
    """Return all pending proposals for similarity comparison."""
    db = await get_db()
    try:
        rows = await (await db.execute(
            "SELECT * FROM proposals WHERE status = 'pending' ORDER BY created_at DESC"
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --------------- Outcome Metrics ---------------

async def upsert_outcome_metrics(
    repo_id: int, week_start: str,
    pr_revision_rounds: float = 0, ci_failure_rate: float = 0,
    review_comment_density: float = 0, time_to_merge_hours: float = 0,
    first_timer_time_to_merge_hours: float = 0, rules_deployed: int = 0,
) -> dict:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO outcome_metrics
               (repo_id, week_start, pr_revision_rounds, ci_failure_rate,
                review_comment_density, time_to_merge_hours,
                first_timer_time_to_merge_hours, rules_deployed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(repo_id, week_start) DO UPDATE SET
                 pr_revision_rounds = excluded.pr_revision_rounds,
                 ci_failure_rate = excluded.ci_failure_rate,
                 review_comment_density = excluded.review_comment_density,
                 time_to_merge_hours = excluded.time_to_merge_hours,
                 first_timer_time_to_merge_hours = excluded.first_timer_time_to_merge_hours,
                 rules_deployed = excluded.rules_deployed,
                 measured_at = datetime('now')""",
            (repo_id, week_start, pr_revision_rounds, ci_failure_rate,
             review_comment_density, time_to_merge_hours,
             first_timer_time_to_merge_hours, rules_deployed),
        )
        await db.commit()
        row = await (await db.execute(
            "SELECT * FROM outcome_metrics WHERE repo_id = ? AND week_start = ?",
            (repo_id, week_start),
        )).fetchone()
        return dict(row)
    finally:
        await db.close()


async def list_outcome_metrics(repo_id: int, limit: int = 12) -> list[dict]:
    db = await get_db()
    try:
        rows = await (await db.execute(
            "SELECT * FROM outcome_metrics WHERE repo_id = ? ORDER BY week_start DESC LIMIT ?",
            (repo_id, limit),
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_rules_with_provenance(repo_id: int | None = None) -> list[dict]:
    """Get rules that have provenance information."""
    db = await get_db()
    try:
        query = "SELECT * FROM knowledge_rules WHERE provenance_url != ''"
        params: list = []
        if repo_id is not None:
            query += " AND repo_id = ?"
            params.append(repo_id)
        query += " ORDER BY confidence DESC"
        rows = await (await db.execute(query, params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def update_rule_provenance(rule_id: int, provenance_url: str, provenance_summary: str) -> dict | None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE knowledge_rules SET provenance_url = ?, provenance_summary = ? WHERE id = ?",
            (provenance_url, provenance_summary, rule_id),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM knowledge_rules WHERE id = ?", (rule_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_rule_paths(rule_id: int, applicable_paths: str) -> dict | None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE knowledge_rules SET applicable_paths = ? WHERE id = ?",
            (applicable_paths, rule_id),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM knowledge_rules WHERE id = ?", (rule_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()

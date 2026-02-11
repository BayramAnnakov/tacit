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
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
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
                      source_type: str, source_ref: str, repo_id: int | None = None) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO knowledge_rules (rule_text, category, confidence, source_type, source_ref, repo_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rule_text, category, confidence, source_type, source_ref, repo_id),
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

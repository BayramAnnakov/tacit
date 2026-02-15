"""Read-only database introspection tools for domain knowledge extraction."""

import json
import re

from claude_agent_sdk import tool

# Module-level connection cache (keyed by connection string hash)
_connections: dict[str, object] = {}


@tool(
    name="db_connect",
    description="Connect to a database (PostgreSQL or SQLite) in read-only mode. Stores the connection for reuse by other db_ tools.",
    input_schema={
        "type": "object",
        "properties": {
            "connection_string": {
                "type": "string",
                "description": "Database connection string. For PostgreSQL: 'postgresql://user:pass@host:port/db'. For SQLite: '/path/to/database.db'",
            },
            "db_type": {
                "type": "string",
                "description": "Database type: 'postgresql' or 'sqlite'",
                "enum": ["postgresql", "sqlite"],
            },
        },
        "required": ["connection_string", "db_type"],
    },
)
async def db_connect(args: dict) -> dict:
    connection_string = args["connection_string"]
    db_type = args["db_type"]
    key = str(hash(connection_string))

    if key in _connections:
        return {"content": [{"type": "text", "text": json.dumps({"connected": True, "db_type": db_type, "info": "Reusing existing connection"})}]}

    if db_type == "postgresql":
        try:
            import asyncpg
        except ImportError:
            return {"content": [{"type": "text", "text": json.dumps({"connected": False, "error": "asyncpg is not installed. Run: pip install asyncpg"})}], "is_error": True}

        conn = await asyncpg.connect(connection_string)
        await conn.execute("SET default_transaction_read_only = ON")
        _connections[key] = conn
        server_version = conn.get_server_version()
        info = f"PostgreSQL {server_version.major}.{server_version.minor}"
    elif db_type == "sqlite":
        import aiosqlite

        conn = await aiosqlite.connect(connection_string)
        await conn.execute("PRAGMA query_only = ON")
        conn.row_factory = aiosqlite.Row
        _connections[key] = conn
        info = f"SQLite database at {connection_string}"
    else:
        return {"content": [{"type": "text", "text": json.dumps({"connected": False, "error": f"Unsupported db_type: {db_type}"})}], "is_error": True}

    return {"content": [{"type": "text", "text": json.dumps({"connected": True, "db_type": db_type, "info": info})}]}


async def _get_connection(connection_string: str, db_type: str):
    """Retrieve a cached connection or create a new one."""
    key = str(hash(connection_string))
    if key not in _connections:
        # Auto-connect
        await db_connect({"connection_string": connection_string, "db_type": db_type})
    return _connections.get(key)


@tool(
    name="db_inspect_schema",
    description="Inspect the full database schema: tables, columns, types, constraints (primary keys, foreign keys, unique, check, not null). Returns structured JSON.",
    input_schema={
        "type": "object",
        "properties": {
            "connection_string": {
                "type": "string",
                "description": "Database connection string",
            },
            "db_type": {
                "type": "string",
                "description": "Database type: 'postgresql' or 'sqlite'",
                "enum": ["postgresql", "sqlite"],
            },
        },
        "required": ["connection_string", "db_type"],
    },
)
async def db_inspect_schema(args: dict) -> dict:
    connection_string = args["connection_string"]
    db_type = args["db_type"]
    conn = await _get_connection(connection_string, db_type)
    if not conn:
        return {"content": [{"type": "text", "text": "Not connected. Call db_connect first."}], "is_error": True}

    schema: dict = {"tables": {}}

    if db_type == "postgresql":
        # Fetch columns
        rows = await conn.fetch(
            """
            SELECT table_name, column_name, data_type, is_nullable,
                   column_default, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        for row in rows:
            table = row["table_name"]
            if table not in schema["tables"]:
                schema["tables"][table] = {"columns": [], "constraints": []}
            schema["tables"][table]["columns"].append({
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
                "max_length": row["character_maximum_length"],
            })

        # Fetch constraints (PK, FK, UNIQUE, CHECK)
        constraint_rows = await conn.fetch(
            """
            SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
                   kcu.column_name,
                   ccu.table_name AS foreign_table_name,
                   ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            LEFT JOIN information_schema.constraint_column_usage AS ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            WHERE tc.table_schema = 'public'
            ORDER BY tc.table_name
            """
        )
        for row in constraint_rows:
            table = row["table_name"]
            if table in schema["tables"]:
                constraint = {
                    "name": row["constraint_name"],
                    "type": row["constraint_type"],
                    "column": row["column_name"],
                }
                if row["constraint_type"] == "FOREIGN KEY":
                    constraint["references"] = {
                        "table": row["foreign_table_name"],
                        "column": row["foreign_column_name"],
                    }
                schema["tables"][table]["constraints"].append(constraint)

        # Fetch CHECK constraint definitions
        check_rows = await conn.fetch(
            """
            SELECT tc.table_name, tc.constraint_name, cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
                ON tc.constraint_name = cc.constraint_name
                AND tc.constraint_schema = cc.constraint_schema
            WHERE tc.table_schema = 'public' AND tc.constraint_type = 'CHECK'
            """
        )
        for row in check_rows:
            table = row["table_name"]
            if table in schema["tables"]:
                schema["tables"][table]["constraints"].append({
                    "name": row["constraint_name"],
                    "type": "CHECK",
                    "definition": row["check_clause"],
                })

    elif db_type == "sqlite":
        # Fetch tables
        cursor = await conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = await cursor.fetchall()

        for table_row in tables:
            table_name = table_row[0]
            create_sql = table_row[1] or ""
            schema["tables"][table_name] = {"columns": [], "constraints": [], "create_sql": create_sql}

            # Fetch columns
            cursor = await conn.execute(f"PRAGMA table_info('{table_name}')")
            columns = await cursor.fetchall()
            for col in columns:
                schema["tables"][table_name]["columns"].append({
                    "name": col[1],
                    "type": col[2],
                    "nullable": col[3] == 0,
                    "default": col[4],
                    "primary_key": col[5] == 1,
                })

            # Fetch foreign keys
            cursor = await conn.execute(f"PRAGMA foreign_key_list('{table_name}')")
            fks = await cursor.fetchall()
            for fk in fks:
                schema["tables"][table_name]["constraints"].append({
                    "type": "FOREIGN KEY",
                    "column": fk[3],
                    "references": {"table": fk[2], "column": fk[4]},
                    "on_update": fk[5],
                    "on_delete": fk[6],
                })

            # Fetch indexes (UNIQUE constraints show up as indexes)
            cursor = await conn.execute(f"PRAGMA index_list('{table_name}')")
            indexes = await cursor.fetchall()
            for idx in indexes:
                if idx[2]:  # unique
                    cursor2 = await conn.execute(f"PRAGMA index_info('{idx[1]}')")
                    idx_cols = await cursor2.fetchall()
                    col_names = [c[2] for c in idx_cols]
                    schema["tables"][table_name]["constraints"].append({
                        "type": "UNIQUE",
                        "name": idx[1],
                        "columns": col_names,
                    })

            # Extract CHECK constraints from CREATE TABLE SQL
            check_pattern = re.compile(r'CHECK\s*\(([^)]+)\)', re.IGNORECASE)
            for match in check_pattern.finditer(create_sql):
                schema["tables"][table_name]["constraints"].append({
                    "type": "CHECK",
                    "definition": match.group(1).strip(),
                })

    return {"content": [{"type": "text", "text": json.dumps(schema, indent=2, default=str)}]}


@tool(
    name="db_sample_data",
    description="Fetch a sample of 10 rows from a database table. Useful for understanding data patterns, formats, and domain terminology.",
    input_schema={
        "type": "object",
        "properties": {
            "connection_string": {
                "type": "string",
                "description": "Database connection string",
            },
            "db_type": {
                "type": "string",
                "description": "Database type: 'postgresql' or 'sqlite'",
                "enum": ["postgresql", "sqlite"],
            },
            "table_name": {
                "type": "string",
                "description": "Name of the table to sample from",
            },
        },
        "required": ["connection_string", "db_type", "table_name"],
    },
)
async def db_sample_data(args: dict) -> dict:
    connection_string = args["connection_string"]
    db_type = args["db_type"]
    table_name = args["table_name"]

    # Validate table name to prevent injection
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
        return {"content": [{"type": "text", "text": "Invalid table name. Only alphanumeric characters and underscores are allowed."}], "is_error": True}

    conn = await _get_connection(connection_string, db_type)
    if not conn:
        return {"content": [{"type": "text", "text": "Not connected. Call db_connect first."}], "is_error": True}

    query = f"SELECT * FROM {table_name} LIMIT 10"

    if db_type == "postgresql":
        rows = await conn.fetch(query)
        result = [dict(row) for row in rows]
    elif db_type == "sqlite":
        cursor = await conn.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        raw_rows = await cursor.fetchall()
        result = [dict(zip(columns, row)) for row in raw_rows]
    else:
        return {"content": [{"type": "text", "text": f"Unsupported db_type: {db_type}"}], "is_error": True}

    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


# Allowed query prefixes (read-only operations)
_ALLOWED_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "DESCRIBE", "PRAGMA")

# Blocked mutation keywords (word boundary match)
_BLOCKED_PATTERN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b',
    re.IGNORECASE,
)


@tool(
    name="db_query_readonly",
    description="Execute a read-only SQL query against the connected database. Only SELECT, WITH, EXPLAIN, SHOW, DESCRIBE, and PRAGMA queries are allowed. Maximum 50 rows returned.",
    input_schema={
        "type": "object",
        "properties": {
            "connection_string": {
                "type": "string",
                "description": "Database connection string",
            },
            "db_type": {
                "type": "string",
                "description": "Database type: 'postgresql' or 'sqlite'",
                "enum": ["postgresql", "sqlite"],
            },
            "query": {
                "type": "string",
                "description": "Read-only SQL query to execute",
            },
        },
        "required": ["connection_string", "db_type", "query"],
    },
)
async def db_query_readonly(args: dict) -> dict:
    connection_string = args["connection_string"]
    db_type = args["db_type"]
    query = args["query"].strip()

    # Validate query starts with an allowed prefix
    upper_query = query.upper().lstrip()
    if not any(upper_query.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        return {
            "content": [{"type": "text", "text": f"Query blocked: must start with one of {', '.join(_ALLOWED_PREFIXES)}"}],
            "is_error": True,
        }

    # Block mutation keywords
    if _BLOCKED_PATTERN.search(query):
        return {
            "content": [{"type": "text", "text": "Query blocked: contains a write operation (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or TRUNCATE)"}],
            "is_error": True,
        }

    conn = await _get_connection(connection_string, db_type)
    if not conn:
        return {"content": [{"type": "text", "text": "Not connected. Call db_connect first."}], "is_error": True}

    # Enforce row limit
    if "LIMIT" not in query.upper():
        query = query.rstrip(";") + " LIMIT 50"

    if db_type == "postgresql":
        rows = await conn.fetch(query)
        result = [dict(row) for row in rows]
    elif db_type == "sqlite":
        cursor = await conn.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        raw_rows = await cursor.fetchall()
        result = [dict(zip(columns, row)) for row in raw_rows]
    else:
        return {"content": [{"type": "text", "text": f"Unsupported db_type: {db_type}"}], "is_error": True}

    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}

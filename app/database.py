import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                category TEXT,
                city TEXT,
                max_results INTEGER NOT NULL,
                filters_json TEXT NOT NULL,
                options_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                found INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                message TEXT,
                output_dir TEXT,
                excel_path TEXT,
                json_path TEXT,
                prompt_path TEXT,
                results_json TEXT,
                logs_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            """
        )
        conn.commit()
        _ensure_column(conn, "jobs", "skipped", "INTEGER DEFAULT 0")
        _ensure_column(conn, "jobs", "options_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "jobs", "json_path", "TEXT")
        _ensure_column(conn, "jobs", "prompt_path", "TEXT")
        _ensure_column(conn, "jobs", "files_cleaned", "INTEGER DEFAULT 0")
        _ensure_column(conn, "jobs", "agent_prompt_path", "TEXT")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS collected_orgs (
                scope_key TEXT NOT NULL,
                org_key TEXT NOT NULL,
                name TEXT,
                job_id TEXT,
                collected_at TEXT NOT NULL,
                PRIMARY KEY (scope_key, org_key)
            );
            CREATE INDEX IF NOT EXISTS idx_collected_orgs_scope ON collected_orgs(scope_key);
            """
        )
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, typedef: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
        conn.commit()


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_job(
    query: str,
    category: str | None,
    city: str | None,
    max_results: int,
    filters: dict[str, bool],
    options: dict[str, Any] | None = None,
) -> str:
    job_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, query, category, city, max_results, filters_json, options_json,
                status, progress, found, total, message, logs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0, 0, 'Ожидание запуска', '[]', ?)
            """,
            (
                job_id,
                query,
                category,
                city,
                max_results,
                json.dumps(filters, ensure_ascii=False),
                json.dumps(options or {}, ensure_ascii=False),
                now,
            ),
        )
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with db() as conn:
        conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)


def append_log(job_id: str, line: str) -> None:
    with db() as conn:
        row = conn.execute("SELECT logs_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        logs = json.loads(row["logs_json"] if row else "[]")
        ts = datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{ts}] {line}")
        conn.execute("UPDATE jobs SET logs_json = ?, message = ? WHERE id = ?", (json.dumps(logs, ensure_ascii=False), line, job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["filters"] = json.loads(data.pop("filters_json"))
    data["options"] = json.loads(data.pop("options_json", "{}") or "{}")
    data["logs"] = json.loads(data.pop("logs_json"))
    if data.get("results_json"):
        data["results"] = json.loads(data["results_json"])
    else:
        data["results"] = []
    data.pop("results_json", None)
    return data


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, query, category, city, status, found, max_results, created_at, finished_at FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def count_collected_orgs(scope_key: str) -> int:
    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM collected_orgs WHERE scope_key = ?",
            (scope_key,),
        ).fetchone()
    return int(row["c"]) if row else 0


def get_collected_org_keys(scope_key: str) -> set[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT org_key FROM collected_orgs WHERE scope_key = ?",
            (scope_key,),
        ).fetchall()
    return {row["org_key"] for row in rows}


def mark_collected_org(scope_key: str, org_key: str, name: str, job_id: str) -> None:
    if not scope_key or not org_key:
        return
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO collected_orgs (scope_key, org_key, name, job_id, collected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(scope_key, org_key) DO UPDATE SET
                name = excluded.name,
                job_id = excluded.job_id,
                collected_at = excluded.collected_at
            """,
            (scope_key, org_key, name, job_id, now),
        )

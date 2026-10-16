"""Connection handling and schema migrations for the persistence layer.

Dual-backend by design (CLAUDE.md session addendum, 2026-07-07): SQLite for
local dev and the full test suite (no `DATABASE_URL` set), Postgres
(Supabase) for the deployed backend (`DATABASE_URL` set as a Vercel
environment variable). This was an explicit decision, not a default --
a local Postgres server isn't installable in the dev sandbox this project
is built in, so tests need to stay on SQLite to remain fast and hermetic.

Every repository and router in this codebase is written once against a
small sqlite3.Connection-shaped surface: `conn.execute(sql, params)`
returning a cursor with `.fetchone()`/`.fetchall()`/`.lastrowid`, plus
`.commit()`/`.rollback()`/`.close()`. SQL text at every call site stays
written in SQLite dialect (`?` placeholders, `PRAGMA foreign_keys`,
`INSERT OR IGNORE`). `_PGConnection` below adapts a psycopg2 connection to
that same surface so repositories and routers never need to know which
backend they're talking to -- all dialect translation lives in this one
module. See `get_connection()`.

Migrations are plain numbered .sql files under `webstaffr/migrations/`,
applied once each and tracked in a `schema_migrations` table -- but only
for the SQLite backend. The Postgres/Supabase schema is managed directly
against the cloud project via the same numbered convention, applied
out-of-band through Supabase migrations, not run by this app at startup
(see `migrate()`).
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger("webstaffr.db")

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Tables whose repositories rely on cursor.lastrowid after a plain INSERT
# (sqlite gives this for free on any INTEGER PRIMARY KEY / rowid table).
# Postgres has no equivalent, so _PGConnection.execute() auto-appends
# `RETURNING <pk>` for inserts into these tables and reads the id back from
# there instead -- see _PGConnection.execute() below.
_LASTROWID_PK = {
    "appointments": "appointment_id",
    "intake_submissions": "submission_id",
    "review_requests": "request_id",
    "review_responses": "response_id",
}


class StorageError(RuntimeError):
    """Raised for any persistence-layer failure. Callers get one clear,
    documented exception type instead of leaking raw sqlite3 or psycopg2
    errors."""


try:
    import psycopg2 as _psycopg2

    _PG_ERRORS: tuple = (_psycopg2.Error,)
except ImportError:  # psycopg2 not installed -- fine when only SQLite is used.
    _PG_ERRORS = ()

# Repositories catch this instead of sqlite3.Error directly, so the same
# except block wraps failures from either backend as StorageError. Import
# from here (`from .db import DB_ERRORS`) rather than importing sqlite3 or
# psycopg2 directly in repository/router modules.
DB_ERRORS: tuple = (sqlite3.Error,) + _PG_ERRORS


def _database_url() -> Optional[str]:
    """DATABASE_URL env var, if set -- selects the Postgres backend. Unset
    in local dev/tests, which stay on SQLite (see module docstring)."""
    return os.environ.get("DATABASE_URL") or None


def using_postgres() -> bool:
    """True if DATABASE_URL is set (the deployed backend). Public wrapper
    around _database_url() for callers outside this module that only need
    the yes/no answer -- e.g. the ASGI lifespan skipping its startup
    connect()/migrate() call entirely under Postgres, since migrate() is
    always a no-op there (see migrate()'s docstring below). That avoids
    making the whole app's cold start -- including DB-independent routes
    like /health -- depend on the database being reachable."""
    return _database_url() is not None


# ---------------------------------------------------------------------------
# Postgres compatibility layer -- see module docstring for why this exists.
# ---------------------------------------------------------------------------


class _PGCursor:
    """Minimal cursor wrapper exposing just what repositories use:
    fetchone/fetchall, plus a lastrowid attribute populated from a
    RETURNING clause where applicable (see _PGConnection.execute)."""

    def __init__(self, raw_cursor) -> None:
        self._raw = raw_cursor
        self.lastrowid: Optional[int] = None

    @property
    def rowcount(self) -> int:
        return self._raw.rowcount if self._raw is not None else 0

    def fetchone(self):
        return self._raw.fetchone() if self._raw is not None else None

    def fetchall(self):
        return self._raw.fetchall() if self._raw is not None else []


class _PGConnection:
    """Wraps a psycopg2 connection to present the sqlite3.Connection surface
    this codebase writes against, translating dialect differences in one
    place instead of at every call site. See module docstring."""

    def __init__(self, raw_conn) -> None:
        self._raw = raw_conn

    def execute(self, sql: str, params: tuple = ()) -> _PGCursor:
        from psycopg2.extras import RealDictCursor

        text = sql.strip()
        upper = text.upper()

        # PRAGMA is SQLite-only (foreign_keys, etc.); Postgres enforces FK
        # constraints unconditionally, so this is a no-op here.
        if upper.startswith("PRAGMA"):
            return _PGCursor(None)

        needs_returning: Optional[str] = None

        # `INSERT OR IGNORE INTO ...` -> `INSERT INTO ... ON CONFLICT DO
        # NOTHING`. Unqualified ON CONFLICT DO NOTHING applies to any
        # unique/PK violation on the table, matching sqlite's OR IGNORE
        # semantics for every call site here (all are tenant-row upserts
        # keyed on their own PK).
        if upper.startswith("INSERT OR IGNORE INTO"):
            text = "INSERT INTO" + text[len("INSERT OR IGNORE INTO"):]
            text = text.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        elif upper.startswith("INSERT INTO") and "RETURNING" not in upper:
            table = text.split()[2]
            pk = _LASTROWID_PK.get(table)
            if pk:
                needs_returning = pk
                text = text.rstrip().rstrip(";") + f" RETURNING {pk}"

        text = text.replace("?", "%s")

        cur = self._raw.cursor(cursor_factory=RealDictCursor)
        cur.execute(text, params)
        wrapped = _PGCursor(cur)
        if needs_returning:
            row = cur.fetchone()
            wrapped.lastrowid = row[needs_returning] if row else None
        return wrapped

    def executescript(self, sql: str) -> None:
        cur = self._raw.cursor()
        cur.execute(sql)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


def get_connection(db_path: str = "webstaffr.db") -> Any:
    """Single connection factory for the whole app. Postgres if DATABASE_URL
    is set (the deployed backend), SQLite at db_path otherwise (local dev,
    and the full test suite). All routers and the migration lifespan call
    this instead of constructing sqlite3.connect()/psycopg2.connect()
    directly, so backend selection lives in exactly one place."""
    database_url = _database_url()
    if database_url:
        import psycopg2

        raw = psycopg2.connect(database_url)
        return _PGConnection(raw)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextlib.contextmanager
def connect(db_path: str) -> Iterator[Any]:
    """Open a connection with sane defaults, commit on success, roll back
    and re-raise (wrapped) on failure, always close.

    `db_path` may be a filesystem path or ":memory:" for tests. Ignored if
    DATABASE_URL is set -- see get_connection().
    """
    try:
        conn = get_connection(db_path)
    except Exception as exc:
        raise StorageError(f"Could not open database at {db_path!r}: {exc}") from exc

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(conn: Any) -> list[str]:
    """Apply any migration under webstaffr/migrations/ not yet recorded as
    applied. Returns the list of migration filenames applied this call
    (empty if the schema was already current, or if the Postgres backend is
    active). Idempotent -- safe to call on every startup.

    Postgres/Supabase schema is managed out-of-band (see module docstring)
    -- this is a deliberate no-op for that backend, not an oversight.
    """
    if _database_url():
        logger.info(
            "migrate_skipped backend=postgres (schema managed via Supabase migrations)"
        )
        return []

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()

    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}

    if not _MIGRATIONS_DIR.is_dir():
        raise StorageError(f"Migrations directory not found: {_MIGRATIONS_DIR}")

    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise StorageError(f"No migration files found in {_MIGRATIONS_DIR}")

    newly_applied = []
    for path in migration_files:
        version = path.stem  # e.g. "0001_initial"
        if version in applied:
            continue
        sql = path.read_text()
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            conn.commit()
            newly_applied.append(version)
            logger.info("migration_applied version=%s", version)
        except sqlite3.Error as exc:
            conn.rollback()
            raise StorageError(f"Migration {version!r} failed: {exc}") from exc

    return newly_applied

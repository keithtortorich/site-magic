"""Unit tests for _PGConnection's SQLite-to-Postgres dialect translation
in db.py -- this is the single most dialect-sensitive piece of code in
the repo, and previously had never been exercised by any test, only
verified by human review plus a smoke test against an
intentionally-unreachable DATABASE_URL that fails at the TCP/auth layer
before any of this rewrite logic ever runs.

No real Postgres connection is used or needed here -- these tests
construct a fake object shaped like psycopg2's connection/cursor surface
(just .cursor()/.execute()/.fetchone()) and assert on the *rewritten SQL
text and params* that _PGConnection hands to it, the same way a real
psycopg2 cursor would receive them. This covers the two rewrite paths
that remain in WebStaffr 4.0: INSERT OR IGNORE -> ON CONFLICT DO
NOTHING, and the RETURNING <pk> auto-append for _LASTROWID_PK tables.
(A third rewrite path -- INSERT OR REPLACE INTO workflow_definitions --
was removed along with the rest of the unused workflow engine; that
table had exactly one caller, and it no longer exists in this repo.)
"""

from __future__ import annotations

import unittest

from webstaffr.db import _PGConnection, _LASTROWID_PK


class _FakeCursor:
    """Records every execute() call (sql, params) so tests can assert on
    the rewritten SQL text, not just its side effects. fetchone()/fetchall()
    return whatever a test pre-loads via _fetchone_result/_fetchall_result --
    mirrors RealDictCursor's dict-row shape (real code accesses
    row[pk_column])."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._fetchone_result = None
        self._fetchall_result: list = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result


class _FakeRawConnection:
    """Shaped like a psycopg2 connection: .cursor(cursor_factory=...)
    returns a cursor, and commit/rollback/close are just recorded, not
    real. One shared _FakeCursor instance (like a real connection handing
    out cursors bound to the same session) so tests can inspect what was
    executed via self.raw.cursor_obj.executed."""

    def __init__(self) -> None:
        self.cursor_factories_requested: list = []
        self.cursor_obj = _FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, cursor_factory=None):
        self.cursor_factories_requested.append(cursor_factory)
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class PGShimTestCase(unittest.TestCase):
    def setUp(self):
        self.raw = _FakeRawConnection()
        self.pg = _PGConnection(self.raw)

    def _last_executed(self):
        return self.raw.cursor_obj.executed[-1]


class TestInsertOrIgnoreRewrite(PGShimTestCase):
    """The generic `INSERT OR IGNORE INTO ...` -> `... ON CONFLICT DO
    NOTHING` rewrite (db.py:149-156), used by every tenant-row upsert in
    the codebase (repository.py, booking.py, intake.py)."""

    def test_or_ignore_is_stripped_and_on_conflict_do_nothing_appended(self):
        self.pg.execute("INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", ("acme",))
        sql, params = self._last_executed()
        self.assertNotIn("OR IGNORE", sql)
        self.assertTrue(sql.strip().startswith("INSERT INTO tenants"))
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertEqual(params, ("acme",))

    def test_placeholder_is_rewritten_to_percent_s(self):
        self.pg.execute("INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", ("acme",))
        sql, _ = self._last_executed()
        self.assertIn("%s", sql)
        self.assertNotIn("?", sql)


class TestUsesRealDictCursor(PGShimTestCase):
    def test_uses_real_dict_cursor(self):
        """RealDictCursor is what makes row['col'] access work identically
        to sqlite3.Row elsewhere in the codebase -- confirm the shim
        actually requests it rather than a plain cursor."""
        self.pg.execute(
            "INSERT INTO appointments (tenant_id, contact_name) VALUES (?, ?)",
            ("acme", "Jane Doe"),
        )
        self.assertEqual(len(self.raw.cursor_factories_requested), 1)
        self.assertIsNotNone(self.raw.cursor_factories_requested[0])


class TestReturningAutoAppend(PGShimTestCase):
    """cursor.lastrowid -> auto-appended RETURNING <pk> for the three
    tables repositories rely on it for (db.py:146-172)."""

    def test_lastrowid_tables_get_returning_appended(self):
        for table, pk in _LASTROWID_PK.items():
            with self.subTest(table=table):
                self.raw.cursor_obj = _FakeCursor()  # fresh cursor per subTest
                self.pg.execute(f"INSERT INTO {table} (tenant_id) VALUES (?)", ("acme",))
                sql, _ = self._last_executed()
                self.assertIn(f"RETURNING {pk}", sql)

    def test_non_lastrowid_table_gets_no_returning(self):
        """tenants has no _LASTROWID_PK entry -- a plain INSERT INTO tenants
        should pass through with only the ? -> %s rewrite, no RETURNING."""
        self.pg.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("acme",))
        sql, _ = self._last_executed()
        self.assertNotIn("RETURNING", sql)

    def test_lastrowid_populated_from_returning_row(self):
        self.raw.cursor_obj._fetchone_result = {"appointment_id": 42}
        cursor = self.pg.execute(
            "INSERT INTO appointments (tenant_id, contact_name, starts_at, created_at) VALUES (?, ?, ?, ?)",
            ("acme", "Jane", "2026-08-01T15:00:00Z", "2026-01-01T00:00:00+00:00"),
        )
        self.assertEqual(cursor.lastrowid, 42)

    def test_lastrowid_is_none_when_no_row_returned(self):
        self.raw.cursor_obj._fetchone_result = None
        cursor = self.pg.execute(
            "INSERT INTO appointments (tenant_id, contact_name, starts_at, created_at) VALUES (?, ?, ?, ?)",
            ("acme", "Jane", "2026-08-01T15:00:00Z", "2026-01-01T00:00:00+00:00"),
        )
        self.assertIsNone(cursor.lastrowid)

    def test_insert_that_already_has_returning_is_not_doubled(self):
        self.pg.execute(
            "INSERT INTO appointments (tenant_id) VALUES (?) RETURNING appointment_id",
            ("acme",),
        )
        sql, _ = self._last_executed()
        self.assertEqual(sql.count("RETURNING"), 1)


class TestPragmaAndPlainQueries(PGShimTestCase):
    def test_pragma_is_a_noop_never_reaches_the_raw_cursor(self):
        cursor = self.pg.execute("PRAGMA foreign_keys = ON")
        self.assertEqual(self.raw.cursor_obj.executed, [])
        self.assertEqual(len(self.raw.cursor_factories_requested), 0)
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(cursor.fetchall(), [])

    def test_select_gets_placeholder_rewrite_only(self):
        self.pg.execute("SELECT * FROM tenants WHERE tenant_id = ?", ("acme",))
        sql, params = self._last_executed()
        self.assertIn("%s", sql)
        self.assertNotIn("?", sql)
        self.assertTrue(sql.strip().startswith("SELECT * FROM tenants"))
        self.assertEqual(params, ("acme",))


class TestConnectionPassThrough(PGShimTestCase):
    """commit/rollback/close/executescript just delegate to the raw
    connection -- confirms the wrapper's non-execute() surface, which the
    rest of the codebase (connect()'s context manager, every router's
    get_connection()) also depends on."""

    def test_commit_delegates(self):
        self.pg.commit()
        self.assertTrue(self.raw.committed)

    def test_rollback_delegates(self):
        self.pg.rollback()
        self.assertTrue(self.raw.rolled_back)

    def test_close_delegates(self):
        self.pg.close()
        self.assertTrue(self.raw.closed)

    def test_executescript_delegates_to_a_plain_cursor(self):
        self.pg.executescript("SELECT 1; SELECT 2;")
        # executescript() uses a plain cursor(), not the RealDictCursor
        # factory used by execute() -- confirm it doesn't reuse cursor_obj's
        # tracked calls in a way that would hide a real bug.
        self.assertEqual(len(self.raw.cursor_factories_requested), 1)
        self.assertIsNone(self.raw.cursor_factories_requested[0])


if __name__ == "__main__":
    unittest.main()

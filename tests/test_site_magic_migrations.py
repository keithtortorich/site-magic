"""Tests that webstaffr/migrations/0016_site_magic.sql (SQLite, auto-applied)
and webstaffr/migrations/postgres_manual/0019_site_magic.sql (Postgres,
applied by hand against Supabase) actually describe the same schema. The two
files are hand-maintained in parallel -- nothing enforces they stay in sync
except a test like this one."""

import os
import re
import tempfile
import unittest
from pathlib import Path

from webstaffr.db import connect, migrate

SQLITE_MIGRATION = Path(__file__).parent.parent / "webstaffr" / "migrations" / "0016_site_magic.sql"
POSTGRES_MIGRATION = (
    Path(__file__).parent.parent / "webstaffr" / "migrations" / "postgres_manual" / "0019_site_magic.sql"
)

EXPECTED_TABLES = {"site_magic_jobs", "site_magic_builds", "site_magic_active_builds"}
EXPECTED_STATUS_VALUES = {
    "queued", "ingesting", "directing", "building", "evaluating",
    "remediating", "final_review", "ready_for_review", "published",
    "failed", "quarantined",
}


def _table_columns(sql: str, table: str) -> set[str]:
    """Pull column names out of a `CREATE TABLE <table> ( ... );` block by
    naive but adequate structural parsing -- both files use one column
    definition per line, which is all this needs to hold."""
    match = re.search(
        rf"CREATE TABLE (?:public\.)?{re.escape(table)}\s*\((.*?)\n\);",
        sql, re.DOTALL,
    )
    assert match, f"CREATE TABLE {table} not found"
    body = match.group(1)
    columns = set()
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("FOREIGN KEY", "PRIMARY KEY", "UNIQUE", "CHECK", "CONSTRAINT")):
            continue
        name = line.split()[0]
        columns.add(name)
    return columns


def _status_check_values(sql: str) -> set[str]:
    match = re.search(r"status TEXT NOT NULL CHECK \(status IN \((.*?)\)\)", sql, re.DOTALL)
    assert match, "status CHECK constraint not found"
    return {v.strip().strip("'") for v in match.group(1).split(",")}


class TestMigrationFilesExist(unittest.TestCase):
    def test_sqlite_migration_file_exists(self):
        self.assertTrue(SQLITE_MIGRATION.is_file())

    def test_postgres_migration_file_exists(self):
        self.assertTrue(POSTGRES_MIGRATION.is_file())


class TestSQLiteMigrationApplies(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.remove(self.db_path)

    def test_migrate_creates_all_three_tables(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            tables = {
                row["name"] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertTrue(EXPECTED_TABLES.issubset(tables))

    def test_migrate_is_idempotent(self):
        with connect(self.db_path) as conn:
            first = migrate(conn)
            second = migrate(conn)
        self.assertIn("0016_site_magic", first)
        self.assertEqual(second, [])

    def test_jobs_table_has_expected_columns(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(site_magic_jobs)")}
        self.assertEqual(
            columns,
            {
                "job_id", "tenant_id", "source_type", "source_payload_json", "status",
                "remediation_rounds", "rebuild_count", "quality_summary_json",
                "final_build_id", "failure_code", "current_event_sequence",
                "created_at", "updated_at",
            },
        )

    def test_builds_table_has_expected_columns(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(site_magic_builds)")}
        self.assertEqual(
            columns,
            {
                "build_id", "job_id", "tenant_id", "artifact_manifest_json",
                "preview_locator", "published_url", "created_at",
            },
        )

    def test_active_builds_table_has_expected_columns(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(site_magic_active_builds)")}
        self.assertEqual(columns, {"tenant_id", "build_id", "activated_at"})

    def test_source_type_check_constraint_rejects_unknown_type(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('acme_hvac')")
            with self.assertRaises(Exception):
                conn.execute(
                    """
                    INSERT INTO site_magic_jobs
                        (job_id, tenant_id, source_type, source_payload_json, status)
                    VALUES ('j1', 'acme_hvac', 'ftp', '{}', 'queued')
                    """
                )

    def test_remediation_rounds_check_constraint_caps_at_two(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('acme_hvac')")
            with self.assertRaises(Exception):
                conn.execute(
                    """
                    INSERT INTO site_magic_jobs
                        (job_id, tenant_id, source_type, source_payload_json, status, remediation_rounds)
                    VALUES ('j1', 'acme_hvac', 'intake', '{}', 'queued', 3)
                    """
                )

    def test_rebuild_count_check_constraint_caps_at_one(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('acme_hvac')")
            with self.assertRaises(Exception):
                conn.execute(
                    """
                    INSERT INTO site_magic_jobs
                        (job_id, tenant_id, source_type, source_payload_json, status, rebuild_count)
                    VALUES ('j1', 'acme_hvac', 'intake', '{}', 'queued', 2)
                    """
                )


class TestSchemaParityWithPostgres(unittest.TestCase):
    """Structural comparison of the two hand-maintained SQL files -- catches
    the two schemas drifting apart (a column added to one and not the
    other, a status value present in one CHECK but not the other)."""

    @classmethod
    def setUpClass(cls):
        cls.sqlite_sql = SQLITE_MIGRATION.read_text()
        cls.postgres_sql = POSTGRES_MIGRATION.read_text()

    def test_both_files_declare_the_same_three_tables(self):
        for table in EXPECTED_TABLES:
            self.assertIn(table, self.sqlite_sql)
            self.assertIn(table, self.postgres_sql)

    def test_jobs_columns_match(self):
        self.assertEqual(
            _table_columns(self.sqlite_sql, "site_magic_jobs"),
            _table_columns(self.postgres_sql, "site_magic_jobs"),
        )

    def test_builds_columns_match(self):
        self.assertEqual(
            _table_columns(self.sqlite_sql, "site_magic_builds"),
            _table_columns(self.postgres_sql, "site_magic_builds"),
        )

    def test_active_builds_columns_match(self):
        self.assertEqual(
            _table_columns(self.sqlite_sql, "site_magic_active_builds"),
            _table_columns(self.postgres_sql, "site_magic_active_builds"),
        )

    def test_status_enum_matches_between_dialects(self):
        sqlite_values = _status_check_values(self.sqlite_sql)
        postgres_values = _status_check_values(self.postgres_sql)
        self.assertEqual(sqlite_values, EXPECTED_STATUS_VALUES)
        self.assertEqual(postgres_values, EXPECTED_STATUS_VALUES)

    def test_remediation_and_rebuild_ceilings_match(self):
        self.assertIn("remediation_rounds BETWEEN 0 AND 2", self.sqlite_sql)
        self.assertIn("remediation_rounds BETWEEN 0 AND 2", self.postgres_sql)
        self.assertIn("rebuild_count BETWEEN 0 AND 1", self.sqlite_sql)
        self.assertIn("rebuild_count BETWEEN 0 AND 1", self.postgres_sql)

    def test_postgres_file_enables_row_level_security_on_all_tables(self):
        for table in EXPECTED_TABLES:
            self.assertIn(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY", self.postgres_sql)

    def test_postgres_file_revokes_default_anon_and_authenticated_access(self):
        """Default-deny RLS: no policy is created here on purpose (the
        service-role worker bypasses RLS), but anon/authenticated must be
        explicitly locked out rather than left to whatever the table
        default grants happen to be."""
        for table in EXPECTED_TABLES:
            self.assertIn(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated", self.postgres_sql)


EVENTS_SQLITE_MIGRATION = (
    Path(__file__).parent.parent / "webstaffr" / "migrations" / "0017_site_magic_job_events.sql"
)
EVENTS_POSTGRES_MIGRATION = (
    Path(__file__).parent.parent / "webstaffr" / "migrations" / "postgres_manual" / "0020_site_magic_job_events.sql"
)


class TestJobEventsMigrationFilesExist(unittest.TestCase):
    def test_sqlite_migration_file_exists(self):
        self.assertTrue(EVENTS_SQLITE_MIGRATION.is_file())

    def test_postgres_migration_file_exists(self):
        self.assertTrue(EVENTS_POSTGRES_MIGRATION.is_file())

    def test_migration_numbers_do_not_collide_with_existing_files(self):
        """0017/0020 were picked by listing the actual migrations directory,
        not guessed -- this pins that they're still free the moment this
        test runs, so a later migration added at the same number fails
        loudly here instead of silently colliding."""
        sqlite_dir = EVENTS_SQLITE_MIGRATION.parent
        other_sqlite_files = [p for p in sqlite_dir.glob("0017_*.sql") if p != EVENTS_SQLITE_MIGRATION]
        self.assertEqual(other_sqlite_files, [])

        pg_dir = EVENTS_POSTGRES_MIGRATION.parent
        other_pg_files = [p for p in pg_dir.glob("0020_*.sql") if p != EVENTS_POSTGRES_MIGRATION]
        self.assertEqual(other_pg_files, [])


class TestSQLiteJobEventsMigrationApplies(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.remove(self.db_path)

    def test_migrate_creates_job_events_table_and_sequence_column(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertIn("site_magic_job_events", tables)
            job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(site_magic_jobs)")}
            self.assertIn("current_event_sequence", job_columns)

    def test_current_event_sequence_defaults_to_zero(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('acme_hvac')")
            conn.execute(
                """
                INSERT INTO site_magic_jobs (job_id, tenant_id, source_type, source_payload_json, status)
                VALUES ('j1', 'acme_hvac', 'intake', '{}', 'queued')
                """
            )
            value = conn.execute(
                "SELECT current_event_sequence FROM site_magic_jobs WHERE job_id = 'j1'"
            ).fetchone()[0]
        self.assertEqual(value, 0)

    def test_duplicate_job_id_event_id_rejected(self):
        with connect(self.db_path) as conn:
            migrate(conn)
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('acme_hvac')")
            conn.execute(
                """
                INSERT INTO site_magic_jobs (job_id, tenant_id, source_type, source_payload_json, status)
                VALUES ('j1', 'acme_hvac', 'intake', '{}', 'queued')
                """
            )
            conn.execute(
                """
                INSERT INTO site_magic_job_events
                    (event_id, job_id, tenant_id, event_sequence, prior_state, new_state, response_json)
                VALUES ('evt_1', 'j1', 'acme_hvac', 1, 'queued', 'ingesting', '{}')
                """
            )
            with self.assertRaises(Exception):
                conn.execute(
                    """
                    INSERT INTO site_magic_job_events
                        (event_id, job_id, tenant_id, event_sequence, prior_state, new_state, response_json)
                    VALUES ('evt_1', 'j1', 'acme_hvac', 2, 'ingesting', 'directing', '{}')
                    """
                )


class TestJobEventsSchemaParityWithPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sqlite_sql = EVENTS_SQLITE_MIGRATION.read_text()
        cls.postgres_sql = EVENTS_POSTGRES_MIGRATION.read_text()

    def test_both_declare_site_magic_job_events(self):
        self.assertIn("site_magic_job_events", self.sqlite_sql)
        self.assertIn("site_magic_job_events", self.postgres_sql)

    def test_columns_match(self):
        self.assertEqual(
            _table_columns(self.sqlite_sql, "site_magic_job_events"),
            _table_columns(self.postgres_sql, "site_magic_job_events"),
        )

    def test_both_add_current_event_sequence_to_jobs(self):
        self.assertIn("current_event_sequence", self.sqlite_sql)
        self.assertIn("current_event_sequence", self.postgres_sql)

    def test_postgres_enables_rls_and_revokes_default_access(self):
        self.assertIn(
            "ALTER TABLE public.site_magic_job_events ENABLE ROW LEVEL SECURITY", self.postgres_sql,
        )
        self.assertIn(
            "REVOKE ALL ON TABLE public.site_magic_job_events FROM anon, authenticated", self.postgres_sql,
        )


if __name__ == "__main__":
    unittest.main()

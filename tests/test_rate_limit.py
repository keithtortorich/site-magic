import unittest
from types import SimpleNamespace
from unittest.mock import patch

from webstaffr.db import connect, migrate
from webstaffr.rate_limit import (
    RateLimitExceeded,
    check_and_increment,
    check_dimensions,
    direct_client_ip,
)


class RateLimitTestCase(unittest.TestCase):
    """Fresh in-memory, migrated DB per test -- same pattern as
    test_repository.py's RepositoryTestCase."""

    def setUp(self):
        self._ctx = connect(":memory:")
        self.conn = self._ctx.__enter__()
        migrate(self.conn)

    def tearDown(self):
        self._ctx.__exit__(None, None, None)


class TestCheckAndIncrement(RateLimitTestCase):
    def test_count_increments_on_each_call(self):
        for expected in (1, 2, 3):
            count = check_and_increment(self.conn, "acme", "chat", max_requests=10)
            self.conn.commit()
            self.assertEqual(count, expected)

    def test_raises_once_over_the_limit(self):
        for _ in range(3):
            check_and_increment(self.conn, "acme", "chat", max_requests=3)
            self.conn.commit()

        with self.assertRaises(RateLimitExceeded):
            check_and_increment(self.conn, "acme", "chat", max_requests=3)

    def test_exceeded_request_still_counts(self):
        """A rejected request still 'used' its slot -- confirms the counter
        keeps incrementing past the limit rather than freezing at max."""
        for _ in range(4):
            try:
                check_and_increment(self.conn, "acme", "chat", max_requests=3)
            except RateLimitExceeded:
                pass
            self.conn.commit()

        row = self.conn.execute(
            "SELECT request_count FROM rate_limit_counters WHERE tenant_id = ? AND endpoint = ?",
            ("acme", "chat"),
        ).fetchone()
        self.assertEqual(row["request_count"], 4)

    def test_tenants_are_tracked_independently(self):
        for _ in range(3):
            check_and_increment(self.conn, "acme", "chat", max_requests=3)
            self.conn.commit()

        # A different tenant hitting the same endpoint has its own budget.
        count = check_and_increment(self.conn, "other-tenant", "chat", max_requests=3)
        self.conn.commit()
        self.assertEqual(count, 1)


class TestDimensionRateLimits(RateLimitTestCase):
    def test_client_ip_ignores_spoofable_forwarding_headers(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="203.0.113.10"),
            headers={"x-forwarded-for": "198.51.100.99"},
        )
        self.assertEqual(direct_client_ip(request), "203.0.113.10")

    def test_each_dimension_has_an_independent_budget(self):
        for _ in range(2):
            check_dimensions(
                self.conn,
                "stripe",
                [("account", "acme"), ("principal", "stripe"), ("ip", "192.0.2.1")],
                max_requests=2,
            )
            self.conn.commit()

        with self.assertRaises(RateLimitExceeded):
            check_dimensions(self.conn, "stripe", [("account", "acme")], max_requests=2)
        self.conn.rollback()

        check_dimensions(self.conn, "stripe", [("account", "other")], max_requests=2)
        self.conn.commit()

    def test_same_key_on_different_dimensions_does_not_collide(self):
        check_dimensions(
            self.conn,
            "retell",
            [("account", "shared"), ("principal", "shared"), ("ip", "shared")],
            max_requests=1,
        )
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT COUNT(*) AS count FROM rate_limit_dimensions WHERE dimension_key = ?",
            ("shared",),
        ).fetchone()
        self.assertEqual(rows["count"], 3)

    def test_endpoints_are_tracked_independently(self):
        for _ in range(3):
            check_and_increment(self.conn, "acme", "chat", max_requests=3)
            self.conn.commit()

        # Same tenant, different endpoint -- separate budget.
        count = check_and_increment(self.conn, "acme", "webhooks_ghl", max_requests=3)
        self.conn.commit()
        self.assertEqual(count, 1)

    def test_new_window_resets_the_count(self):
        for _ in range(3):
            check_and_increment(self.conn, "acme", "chat", max_requests=3, window_seconds=60)
            self.conn.commit()

        with self.assertRaises(RateLimitExceeded):
            check_and_increment(self.conn, "acme", "chat", max_requests=3, window_seconds=60)

        # Simulate the window rolling over by advancing the clock rather
        # than waiting 60 real seconds.
        with patch("webstaffr.rate_limit.time.time", return_value=__import__("time").time() + 61):
            count = check_and_increment(self.conn, "acme", "chat", max_requests=3, window_seconds=60)
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()

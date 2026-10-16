import os
import tempfile
import threading
import time
from unittest.mock import patch

from webstaffr.db import get_connection, migrate
from webstaffr.webhook_replay import claim_delivery, complete_delivery


def test_claim_is_atomic_and_duplicate_returns_stored_response():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = get_connection(path)
        migrate(conn)
        first = claim_delivery(
            conn, provider="stripe", event_key="evt_1", event_type="charge.succeeded",
            raw_body=b"{}", tenant_id="acme",
        )
        assert first.is_new
        complete_delivery(conn, provider="stripe", event_key="evt_1", response_json='{"status":"ok"}')
        conn.commit()

        duplicate = claim_delivery(
            conn, provider="stripe", event_key="evt_1", event_type="charge.succeeded",
            raw_body=b"{}", tenant_id="acme",
        )
        assert not duplicate.is_new
        assert duplicate.response_json == '{"status":"ok"}'
        conn.rollback()
        conn.close()
    finally:
        os.remove(path)


def test_rolled_back_claim_can_be_retried():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = get_connection(path)
        migrate(conn)
        assert claim_delivery(
            conn, provider="retell", event_key="call_1", event_type="call_started",
            raw_body=b"{}", tenant_id="acme",
        ).is_new
        conn.rollback()
        assert claim_delivery(
            conn, provider="retell", event_key="call_1", event_type="call_started",
            raw_body=b"{}", tenant_id="acme",
        ).is_new
        conn.rollback()
        conn.close()
    finally:
        os.remove(path)


def test_concurrent_duplicate_has_exactly_one_winner():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        setup = get_connection(path)
        migrate(setup)
        setup.close()
        barrier = threading.Barrier(2)
        results = []

        def worker(delay: float) -> None:
            conn = get_connection(path)
            barrier.wait()
            claim = claim_delivery(
                conn, provider="stripe", event_key="evt_concurrent",
                event_type="charge.succeeded", raw_body=b"{}", tenant_id="acme",
            )
            results.append(claim.is_new)
            if claim.is_new:
                time.sleep(delay)
                complete_delivery(
                    conn, provider="stripe", event_key="evt_concurrent", response_json="{}"
                )
            conn.commit()
            conn.close()

        first = threading.Thread(target=worker, args=(0.1,))
        second = threading.Thread(target=worker, args=(0,))
        first.start()
        second.start()
        first.join()
        second.join()
        assert sorted(results) == [False, True]
    finally:
        os.remove(path)


def test_claim_prunes_records_older_than_retention_window():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = get_connection(path)
        migrate(conn)
        with patch("webstaffr.webhook_replay.time.time", return_value=1_000_000):
            assert claim_delivery(
                conn, provider="stripe", event_key="old", event_type="test",
                raw_body=b"old", tenant_id="acme",
            ).is_new
            conn.commit()
        with patch("webstaffr.webhook_replay.time.time", return_value=1_604_801):
            assert claim_delivery(
                conn, provider="stripe", event_key="new", event_type="test",
                raw_body=b"new", tenant_id="acme",
            ).is_new
            conn.commit()
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM webhook_deliveries WHERE event_key = ?", ("old",)
        ).fetchone()
        assert row["count"] == 0
        conn.close()
    finally:
        os.remove(path)

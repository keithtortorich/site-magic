"""Focused smoke tests for the workflow graph HTTP router
(webstaffr/workers/angel/workflow_graph_router.py).

Complements tests/test_workflow_graph.py, which covers the
integrations/workflow_graph/ persistence layer directly. This file
exercises the same behavior through real HTTP calls via FastAPI's
TestClient -- the stronger signal, since it proves the router wiring,
request/response shapes, and auth actually work end to end, not just the
underlying repository functions in isolation.

Every test gets its own temp-file SQLite database via the `db_path`
fixture below (mirrors test_router.py's per-test-class tempfile
convention). A bare create_app() with no db_path defaults to the shared
"webstaffr.db" file on disk -- fine for a single ad-hoc run, but multiple
tests in one file would otherwise collide on the same
(tenant_id, workflow_instance_id, node_id) rows across test runs, since
execution_nodes' primary key is exactly that triple. Caught this the hard
way during development: two tests reusing "tenant-1"/"wf-1"/"root-1"
against the shared default db file produced a real
sqlite3.IntegrityError (UNIQUE constraint failed) that had nothing to do
with either test's actual logic.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webstaffr.workers.angel.api_auth import NullSharedSecretVerifier, StaticSecretVerifier
from webstaffr.app import create_app


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "test_workflow_graph.db")
    yield path
    if os.path.exists(path):
        os.remove(path)


def _all_route_paths(routes) -> list[str]:
    """See test_social_media_integration.py's identical helper for why
    this recursion (via original_router) is needed rather than a flat
    route.path check -- FastAPI 0.139.2 wraps each include_router() call
    in an internal _IncludedRouter object."""
    found: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            found.append(path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            found.extend(_all_route_paths(original_router.routes))
    return found


def _test_app(db_path: str):
    return create_app(
        db_path=db_path,
        workflow_graph_verifier=NullSharedSecretVerifier(),
    )


def test_workflow_graph_routes_are_registered(db_path) -> None:
    app = _test_app(db_path)
    paths = [p for p in _all_route_paths(app.routes) if "/workflow-graph" in p]
    assert "/workflow-graph/nodes" in paths
    assert any(p.startswith("/workflow-graph/nodes/") and p.endswith("/status") for p in paths)


def test_create_and_get_node(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        create_resp = http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "intake",
                "status": "completed",
                "payload_ref": "intake/submission-1",
            },
        )
        assert create_resp.status_code == 200
        data = create_resp.json()
        assert data["node_id"] == "root-1"
        assert data["type"] == "intake"
        assert data["status"] == "completed"
        assert data["parent_node_id"] is None
        assert "created_at" in data

        get_resp = http.get(
            "/workflow-graph/nodes/wf-1/root-1",
            params={"tenant_id": "tenant-1"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["node_id"] == "root-1"


def test_create_node_rejects_bad_type(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        resp = http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "not_a_real_type",
                "status": "completed",
            },
        )
        assert resp.status_code == 400


def test_create_node_rejects_invalid_tenant(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        resp = http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "intake",
                "status": "completed",
            },
        )
        assert resp.status_code == 400


def test_get_node_not_found(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        resp = http.get(
            "/workflow-graph/nodes/wf-does-not-exist/node-does-not-exist",
            params={"tenant_id": "tenant-1"},
        )
        assert resp.status_code == 404


def test_list_nodes_returns_full_trace_with_parent_linkage(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "campaign",
                "status": "active",
            },
        )
        http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "approval-1",
                "type": "approval",
                "status": "pending",
                "parent_node_id": "root-1",
            },
        )

        list_resp = http.get(
            "/workflow-graph/nodes/wf-1",
            params={"tenant_id": "tenant-1"},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["workflow_instance_id"] == "wf-1"
        node_ids = [n["node_id"] for n in data["nodes"]]
        assert node_ids == ["root-1", "approval-1"]
        assert data["nodes"][1]["parent_node_id"] == "root-1"


def test_update_node_status_transitions_atomically(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "publish-1",
                "type": "publish_job",
                "status": "pending",
            },
        )

        update_resp = http.post(
            "/workflow-graph/nodes/wf-1/publish-1/status",
            params={"tenant_id": "tenant-1"},
            json={"status": "completed", "completed_at": "2026-07-24T00:00:00+00:00"},
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["status"] == "completed"
        assert data["completed_at"] == "2026-07-24T00:00:00+00:00"


def test_update_node_status_not_found(db_path) -> None:
    app = _test_app(db_path)
    with TestClient(app) as http:
        resp = http.post(
            "/workflow-graph/nodes/wf-none/node-none/status",
            params={"tenant_id": "tenant-1"},
            json={"status": "completed"},
        )
        assert resp.status_code == 404


def test_workflow_graph_auth_rejects_missing_or_wrong_key(db_path) -> None:
    """Dependency-injects a real StaticSecretVerifier via
    create_app(workflow_graph_verifier=...) -- same approach
    test_router.py's TestBookApiKeyAuth uses for /book, rather than
    mutating process env vars and reloading modules. See
    workflow_graph_router.py's module docstring for why this router is
    built to support DI (unlike social_media_router.py, which predates
    this pattern)."""
    app = create_app(db_path=db_path, workflow_graph_verifier=StaticSecretVerifier("test-secret"))
    with TestClient(app) as http:
        resp = http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "intake",
                "status": "completed",
            },
        )
        assert resp.status_code == 401

        resp_wrong = http.post(
            "/workflow-graph/nodes",
            headers={"X-API-Key": "wrong-key"},
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "intake",
                "status": "completed",
            },
        )
        assert resp_wrong.status_code == 401

        resp_ok = http.post(
            "/workflow-graph/nodes",
            headers={"X-API-Key": "test-secret"},
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "intake",
                "status": "completed",
            },
        )
        assert resp_ok.status_code == 200


def test_workflow_graph_unconfigured_defaults_to_closed(db_path) -> None:
    """Production construction denies access when the key is absent."""
    assert os.environ.get("WORKFLOW_GRAPH_API_KEY") is None, (
        "WORKFLOW_GRAPH_API_KEY must not be set in the test environment -- "
        "this regression test requires an unconfigured environment."
    )
    app = create_app(db_path=db_path)
    with TestClient(app) as http:
        response = http.post(
            "/workflow-graph/nodes",
            json={
                "tenant_id": "tenant-1",
                "workflow_instance_id": "wf-1",
                "node_id": "root-1",
                "type": "intake",
                "status": "completed",
            },
        )
    assert response.status_code == 401

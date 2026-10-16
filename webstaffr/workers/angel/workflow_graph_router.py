"""FastAPI router for the retained workflow graph (execution-trace model).

Mounted into the main app via
create_app().include_router(create_workflow_graph_router(verifier=...))
in webstaffr/workers/angel/router.py.

Exposes read/write access to webstaffr/integrations/workflow_graph/ so
callers (the social-media-marketing bridge today, other workflow-spanning
features later) can record and query execution-trace nodes over HTTP
rather than only in-process. Server-to-server only, same reasoning as
/book and /webhooks/ghl -- not added to ScopedCORSMiddleware's paths.

Auth is dependency-injected via create_workflow_graph_router(verifier=...)
rather than resolved from an env var at module-import time -- this
follows create_app()'s own established pattern for retell_verifier/
ghl_webhook_verifier/book_api_verifier (see router.py and
test_router.py's TestBookApiKeyAuth), which supports real unit tests that
inject a StaticSecretVerifier directly instead of mutating process env
vars and reloading modules. social_media_router.py predates this and
still uses the env-var-at-import-time shape; that's a pre-existing
narrower-coverage gap in that router, not a pattern to repeat here.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from .api_auth import (
    DenyAllSharedSecretVerifier,
    SharedSecretVerifier,
    StaticSecretVerifier,
)
from ...db import DB_ERRORS, get_connection
from ...integrations.workflow_graph.client import WorkflowGraphClient, WorkflowGraphError
from ...tenant import InvalidTenantError, Tenant


def workflow_graph_verifier_from_env() -> SharedSecretVerifier:
    """Return a real verifier when configured, otherwise deny all."""
    secret = os.environ.get("WORKFLOW_GRAPH_API_KEY")
    if secret:
        return StaticSecretVerifier(secret)
    return DenyAllSharedSecretVerifier()


def create_workflow_graph_router(verifier: Optional[SharedSecretVerifier] = None) -> APIRouter:
    """Factory rather than a module-level router instance, so tests (and
    create_app()) can inject a specific verifier instead of depending on
    process env vars -- same reasoning as create_app() itself being a
    factory (see router.py's create_app docstring)."""
    active_verifier = verifier or workflow_graph_verifier_from_env()
    router = APIRouter()

    def _require_auth(x_api_key: Optional[str]) -> None:
        if not active_verifier.verify(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    def _validate_tenant(tenant_id: str) -> None:
        try:
            Tenant(tenant_id=tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/workflow-graph/nodes")
    def create_node(
        req: CreateNodeRequest,
        request: Request,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> dict:
        _require_auth(x_api_key)
        _validate_tenant(req.tenant_id)

        conn = _get_connection(request)
        try:
            client = WorkflowGraphClient(conn=conn)
            try:
                node = client.create_node(
                    tenant_id=req.tenant_id,
                    workflow_instance_id=req.workflow_instance_id,
                    node_id=req.node_id,
                    type=req.type,
                    status=req.status,
                    payload_ref=req.payload_ref,
                    parent_node_id=req.parent_node_id,
                )
            except ValueError as exc:
                # create_node/sync.create_node raise plain ValueError for a
                # bad type/status (see VALID_NODE_TYPES/VALID_STATUSES) --
                # a client mistake, not a server failure, so this is a
                # 400, not a 503 (WorkflowGraphError below is reserved
                # for integration/config failures, per its own
                # docstring).
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            conn.commit()
        except WorkflowGraphError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        finally:
            conn.close()

        return _node_to_dict(node)

    @router.get("/workflow-graph/nodes/{workflow_instance_id}/{node_id}")
    def get_node(
        workflow_instance_id: str,
        node_id: str,
        tenant_id: str,
        request: Request,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> dict:
        _require_auth(x_api_key)
        _validate_tenant(tenant_id)

        conn = _get_connection(request)
        try:
            client = WorkflowGraphClient(conn=conn)
            node = client.get_node(
                tenant_id=tenant_id,
                workflow_instance_id=workflow_instance_id,
                node_id=node_id,
            )
        finally:
            conn.close()

        if node is None:
            raise HTTPException(status_code=404, detail="No workflow graph node found")

        return _node_to_dict(node)

    @router.get("/workflow-graph/nodes/{workflow_instance_id}")
    def list_nodes(
        workflow_instance_id: str,
        tenant_id: str,
        request: Request,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> dict:
        """Every node for one workflow_instance_id, oldest first -- enough
        to reconstruct the full execution trace client-side by following
        parent_node_id links."""
        _require_auth(x_api_key)
        _validate_tenant(tenant_id)

        conn = _get_connection(request)
        try:
            client = WorkflowGraphClient(conn=conn)
            nodes = client.list_nodes(tenant_id=tenant_id, workflow_instance_id=workflow_instance_id)
        finally:
            conn.close()

        return {
            "tenant_id": tenant_id,
            "workflow_instance_id": workflow_instance_id,
            "nodes": [_node_to_dict(n) for n in nodes],
        }

    @router.post("/workflow-graph/nodes/{workflow_instance_id}/{node_id}/status")
    def update_node_status(
        workflow_instance_id: str,
        node_id: str,
        tenant_id: str,
        req: UpdateNodeStatusRequest,
        request: Request,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> dict:
        _require_auth(x_api_key)
        _validate_tenant(tenant_id)

        conn = _get_connection(request)
        try:
            client = WorkflowGraphClient(conn=conn)
            try:
                node = client.update_node_status(
                    tenant_id=tenant_id,
                    workflow_instance_id=workflow_instance_id,
                    node_id=node_id,
                    status=req.status,
                    completed_at=req.completed_at,
                    failure_reason=req.failure_reason,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            conn.commit()
        finally:
            conn.close()

        if node is None:
            raise HTTPException(status_code=404, detail="No workflow graph node found")

        return _node_to_dict(node)

    return router


def _get_connection(request: Request):
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="Workflow graph temporarily unavailable") from exc


class CreateNodeRequest(BaseModel):
    tenant_id: str
    workflow_instance_id: str
    node_id: str
    type: str
    status: str
    payload_ref: Optional[str] = None
    parent_node_id: Optional[str] = None


class UpdateNodeStatusRequest(BaseModel):
    status: str
    completed_at: Optional[str] = None
    failure_reason: Optional[str] = None


def _node_to_dict(node) -> dict:
    return {
        "node_id": node.node_id,
        "tenant_id": node.tenant_id,
        "workflow_instance_id": node.workflow_instance_id,
        "type": node.type,
        "status": node.status,
        "payload_ref": node.payload_ref,
        "parent_node_id": node.parent_node_id,
        "created_at": node.created_at,
        "completed_at": node.completed_at,
        "failure_reason": node.failure_reason,
    }

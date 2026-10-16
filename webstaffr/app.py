"""Composition root -- builds the FastAPI app and wires every router.

This is the single place that assembles the full HTTP surface: Angel
(chat/book/GHL-webhook), Retell voice webhooks, intake, site-data,
attribution, and the two integration bridges (social-media-marketing,
workflow-graph). A future AI-employee worker (e.g. Marketing
Coordinator) adds its own router here, as a sibling to Angel's -- never
nested inside workers/angel/.

Split out of workers/angel/router.py during the WebStaffr 4.0 rebuild:
that file had grown into both the app factory AND Angel's own
endpoints, which buried this repo's actual composition root four
directories deep, under one specific AI worker's package. Angel's own
request/response models and endpoint handlers stayed in
workers/angel/router.py as create_angel_router(); this file combines
everything into one FastAPI app.
"""

from __future__ import annotations

import logging
import os as _os
from contextlib import asynccontextmanager
from typing import AbstractSet, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .agency_router import agency_router
from .attribution_router import create_attribution_router
from .auth_router import create_auth_router
from .custom_domain_middleware import CustomDomainMiddleware
from .customer_auth import CustomerAuthorizer, IdentityVerifier, identity_verifier_from_env
from .dashboard_router import dashboard_router
from .db import connect, migrate, using_postgres
from .demo_router import demo_router
from .intake_router import intake_router
from .landing_router import landing_router
from .site_render_router import site_render_router
from .site_router import site_router
from .site_magic import ArtifactStorage, NullSiteMagicQueue, SiteMagicQueue
from .site_magic_control import SiteMagicBuildDispatcher, SiteMagicPublisher
from .site_magic_control_router import create_site_magic_control_router
from .site_magic_ui_router import site_magic_ui_router
from .site_magic_router import create_site_magic_router
from .website_lead_router import create_website_lead_router
from .security_middleware import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from .workers.angel.api_auth import SharedSecretVerifier, internal_api_verifier_from_env
from .workers.angel.ghl import GHLClient
from .workers.angel.retell import RetellWebhookVerifier
from .workers.angel.retell_router import create_retell_router
from .workers.angel.router import create_angel_router
from .workers.angel.social_media_router import social_media_router
from .workers.angel.voice import VoiceBackend
from .workers.angel.workflow_graph_router import create_workflow_graph_router
from .workers.rita.router import create_rita_router
from .workers.leo.router import create_leo_router
from .workers.sam.router import create_sam_router

try:  # optional in minimal test/runtime envs without ServiceTitan configured
    from .integrations.servicetitan import ServiceTitanSync as _ServiceTitanSync
except Exception:  # noqa: BLE001
    _ServiceTitanSync = None  # type: ignore[assignment,misc]

# Optional external TTS backend. When KOKORO_TTS_URL is set, /v1/audio/speech
# proxies OpenAI-compatible speech requests to that backend instead of
# requiring any new dependency or model hosting inside this repo.
_KOKORO_TTS_URL = _os.environ.get("KOKORO_TTS_URL")

# Expose under the public module name so test patches and any future
# direct imports resolve consistently, while preserving the existing
# lazy-import fallback behavior inside the handler below.
ServiceTitanSync = _ServiceTitanSync

logger = logging.getLogger("webstaffr.app")

# CORS configuration: allowlist of origins that may access browser-facing
# endpoints with credentials (cookies). Default to localhost for development.
_ALLOWED_ORIGINS = _os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

# Paths called directly from browser JS running on an arbitrary origin --
# the customer-site widget (angel-widget.js) for /chat, the intake form
# for /intake and its read-only presets endpoints, and the customer site's
# client-side fetch of its own content for /sites/{tenant_id}. These are
# the only paths that need CORS headers. /book and /webhooks/ghl are not
# meant to be readable by browser JS running on an arbitrary third-party
# origin -- /webhooks/ghl is only ever called server-to-server by
# GoHighLevel (CORS is a browser-enforced restriction and has no bearing
# on that caller), and /book has no browser caller today. Scoping here
# means adding a browser-facing caller for /book later requires a
# deliberate change to this set, not an accidental side effect of an
# app-wide wildcard.
_PUBLIC_CORS_PATHS = {"/chat", "/intake"}
_PRIVATE_CORS_PATHS = {"/auth/session", "/auth/logout"}
# /tenants/{tenant_id}/{metrics,calls,tracking-number} are read by the
# customer dashboard client-side, same reasoning as /sites/{tenant_id} --
# see _CORS_SCOPED_PREFIXES below, where the actual prefix is registered
# (a dynamic path segment can't be listed here as an exact match).
# Prefixes rather than exact paths, for routes with a path parameter
# (/intake/presets/{industry}, /sites/{tenant_id}) -- exact-match
# membership in _CORS_SCOPED_PATHS can't match a dynamic segment.
_PUBLIC_CORS_PREFIXES = ("/intake/presets", "/sites/")
_PRIVATE_CORS_PREFIXES = ("/tenants/", "/site-magic/", "/v1/tenants/")
_SERVICETITAN_POLL_PATH = "/integrations/servicetitan/poll"


def _customer_allowed_origins_from_env() -> frozenset[str]:
    """Parse exact private-dashboard origins; wildcard and URL paths are invalid."""
    raw = _os.environ.get("CUSTOMER_ALLOWED_ORIGINS", "")
    origins: set[str] = set()
    for item in raw.split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("CUSTOMER_ALLOWED_ORIGINS must contain exact http(s) origins")
        origins.add(origin)
    return frozenset(origins)


class ScopedCORSMiddleware(BaseHTTPMiddleware):
    """Keep public embed CORS separate from private credentialed CORS.

    Public widget/intake routes remain readable from arbitrary customer
    sites. Auth and dashboard routes accept cross-origin requests only from
    exact configured origins and emit credentials support for a future
    HttpOnly-cookie transport. Moving tokens into cookies additionally
    requires CSRF protection and a deliberate SameSite policy review.
    """

    def __init__(self, app, customer_allowed_origins: AbstractSet[str]):
        super().__init__(app)
        self._customer_allowed_origins = frozenset(customer_allowed_origins)

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        path = request.url.path
        public = path in _PUBLIC_CORS_PATHS or path.startswith(_PUBLIC_CORS_PREFIXES)
        private = path in _PRIVATE_CORS_PATHS or path.startswith(_PRIVATE_CORS_PREFIXES)
        private_origin_allowed = private and origin in self._customer_allowed_origins

        if private and origin and not private_origin_allowed:
            return Response(status_code=403)
        if (public or private_origin_allowed) and request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        if public and origin:
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
        elif private_origin_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Correlation-ID"
            )
            response.headers["Vary"] = "Origin"

        return response


def create_app(
    db_path: str = "webstaffr.db",
    voice_backend: Optional[VoiceBackend] = None,
    ghl_client: Optional[GHLClient] = None,
    ghl_messaging_client: Optional = None,  # For Leo's outreach (SMS/email)
    retell_verifier: Optional[RetellWebhookVerifier] = None,
    ghl_webhook_verifier: Optional[SharedSecretVerifier] = None,
    book_api_verifier: Optional[SharedSecretVerifier] = None,
    workflow_graph_verifier: Optional[SharedSecretVerifier] = None,
    stripe_webhook_verifier: Optional[SharedSecretVerifier] = None,
    internal_api_verifier: Optional[SharedSecretVerifier] = None,
    customer_identity_verifier: Optional[IdentityVerifier] = None,
    customer_allowed_origins: Optional[AbstractSet[str]] = None,
    site_magic_queue: Optional[SiteMagicQueue] = None,
    site_magic_artifact_storage: Optional[ArtifactStorage] = None,
    max_request_body_bytes: int = 1_048_576,
    site_magic_build_dispatcher: Optional[SiteMagicBuildDispatcher] = None,
    site_magic_publisher: Optional[SiteMagicPublisher] = None,
) -> FastAPI:
    """Factory rather than a module-level app instance, so tests (and any
    future multi-tenant deployment shape) can construct an app pointed at
    a specific database and specific backends instead of relying on
    hidden global state.

    IMPORTANT: this module also builds a default `app` instance at import
    time (see bottom of file), for `uvicorn ...:app`. Migration must NOT
    run eagerly inside this factory itself -- that would make merely
    importing this module (as every test and the health check does) touch
    disk and create/migrate a real db file as a side effect, independent
    of whether that app instance is ever actually served. Migration stays
    scoped to the ASGI lifespan event below, which only fires when the
    app is actually started.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Under Postgres, migrate() is a documented no-op (schema is managed
        # out-of-band via Supabase migrations) -- so skip opening a
        # connection at all rather than making the whole app's cold start
        # (including DB-independent routes like /health) depend on the
        # database being reachable. A transient outage on the Postgres side
        # should degrade DB-touching routes, not take down the entire app.
        if not using_postgres():
            with connect(db_path) as conn:
                migrate(conn)
        yield

    app = FastAPI(title="NetBuild.Pro", lifespan=lifespan)
    app.state.db_path = db_path  # read by intake_router's/site_router's _get_connection()
    active_internal_api_verifier = internal_api_verifier or internal_api_verifier_from_env()
    active_site_magic_build_dispatcher = site_magic_build_dispatcher or _site_magic_control_build_dispatcher_from_env()
    active_site_magic_publisher = site_magic_publisher
    if active_site_magic_publisher is None and site_magic_artifact_storage is not None:
        from .site_magic_adapters import ArtifactStorageSiteMagicPublisher
        active_site_magic_publisher = ArtifactStorageSiteMagicPublisher(site_magic_artifact_storage)
    customer_authorizer = CustomerAuthorizer(
        customer_identity_verifier or identity_verifier_from_env()
    )
    app.state.internal_api_verifier = active_internal_api_verifier
    app.state.customer_authorizer = customer_authorizer
    # Resolved once here (not left to create_site_magic_router()'s own
    # defaulting) so intake_router's post-commit auto-enqueue hook uses the
    # exact same queue instance the Site Magic API itself enqueues through.
    resolved_site_magic_queue = site_magic_queue or NullSiteMagicQueue()
    app.state.site_magic_queue = resolved_site_magic_queue
    # Read by demo_router.py, same reasoning as site_magic_queue above:
    # demo_job_manager.py auto-publishes a demo once its build is ready
    # and needs the exact same ArtifactStorage instance create_site_magic_router()
    # is wired with below, not a second default that could silently diverge.
    app.state.site_magic_artifact_storage = site_magic_artifact_storage
    app.include_router(landing_router)
    app.include_router(agency_router)
    app.include_router(demo_router)
    app.include_router(intake_router)
    app.include_router(site_router)
    app.include_router(site_render_router)
    app.include_router(create_website_lead_router(ghl_client=ghl_client))
    app.include_router(create_auth_router(customer_authorizer))
    app.include_router(create_attribution_router(customer_authorizer))
    app.include_router(
        dashboard_router
    )
    app.include_router(site_magic_ui_router)
    app.include_router(
        create_site_magic_control_router(
            customer_authorizer,
            internal_api_verifier=active_internal_api_verifier,
            build_dispatcher=active_site_magic_build_dispatcher,
            publisher=active_site_magic_publisher,
        )
    )
    app.include_router(
        create_site_magic_router(
            customer_authorizer,
            queue=resolved_site_magic_queue,
            artifact_storage=site_magic_artifact_storage,
            internal_api_verifier=active_internal_api_verifier,
        )
    )
    app.include_router(social_media_router)
    app.include_router(create_workflow_graph_router(verifier=workflow_graph_verifier))
    # /retell/* is server-to-server only (Retell calling this app, not a
    # browser) -- intentionally not added to ScopedCORSMiddleware's paths,
    # same reasoning as /book and /webhooks/ghl.
    app.include_router(
        create_retell_router(
            db_path=db_path,
            voice_backend=voice_backend,
            ghl_client=ghl_client,
            verifier=retell_verifier,
        )
    )
    # Angel's own endpoints (/chat, /book, /webhooks/ghl) live in
    # workers/angel/router.py -- this is the only place that worker's
    # router gets included, same pattern every future AI-employee worker
    # will follow (its own create_<worker>_router() included here).
    app.include_router(
        create_angel_router(
            db_path=db_path,
            voice_backend=voice_backend,
            ghl_client=ghl_client,
            book_api_verifier=book_api_verifier,
            ghl_webhook_verifier=ghl_webhook_verifier,
            stripe_webhook_verifier=stripe_webhook_verifier,
        )
    )
    # Rita's endpoints (/webhooks/ghl/job_completed, /workers/rita/draft-response)
    # -- reputation management: automate review requests and response drafting.
    app.include_router(
        create_rita_router(
            db_path=db_path,
            ghl_client=ghl_client,
            ghl_webhook_verifier=ghl_webhook_verifier,
            internal_api_verifier=active_internal_api_verifier,
        )
    )
    # Leo's endpoints (/webhooks/ghl/lead, /leo/score) -- instantaneous
    # lead follow-up with AOKAI scoring and first-touch outreach.
    app.include_router(
        create_leo_router(
            db_path=db_path,
            # Deliberately separate from the general GHL client. Configuring
            # CRM sync for Angel must not silently activate automated SMS or
            # email outreach before the TCPA/DNC gate is cleared.
            ghl_messaging_client=ghl_messaging_client,
            ghl_webhook_verifier=ghl_webhook_verifier,
            internal_api_verifier=active_internal_api_verifier,
        )
    )
    # Sam's endpoints (/quotes/generate, /quotes/{id}, /quotes/{id}/accept) --
    # quote generation, objection handling, and quote-to-booking conversion.
    # Server-to-server only, no CORS.
    app.include_router(
        create_sam_router(
            db_path=db_path,
            ghl_client=ghl_client,
            internal_api_verifier=active_internal_api_verifier,
        )
    )

    # Custom domain middleware rewrites requests to custom domains to the
    # internal /sites/{tenant_id}/web routing structure via Host header lookup.
    # Must run before CORS (and most other middleware) so path rewriting happens
    # before routing decisions are made.
    app.add_middleware(CustomDomainMiddleware)

    # The widget is embedded on customer websites (arbitrary origins), so
    # /chat needs CORS enabled; the intake form (wherever it's hosted) needs
    # the same for /intake. Scoped to just those paths -- see
    # ScopedCORSMiddleware above -- rather than an app-wide wildcard, which
    # would also cover /book and /webhooks/ghl as an unintended side effect.
    app.add_middleware(
        ScopedCORSMiddleware,
        customer_allowed_origins=(
            frozenset(customer_allowed_origins)
            if customer_allowed_origins is not None
            else _customer_allowed_origins_from_env()
        ),
    )
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_request_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    def health() -> dict:
        payload = {"status": "ok"}
        release = _os.environ.get("VERCEL_GIT_COMMIT_SHA", "").strip()
        if release:
            payload["release"] = release
        return payload

    if _KOKORO_TTS_URL:
        @app.post("/v1/audio/speech")
        async def proxy_kokoro_speech(request: Request) -> Response:
            """Proxy OpenAI-compatible TTS requests to Kokoro when KOKORO_TTS_URL is configured.

            Keeps this app free of model hosting or new dependencies.
            """
            import httpx as _httpx

            url = f"{_KOKORO_TTS_URL.rstrip('/')}/v1/audio/speech"
            body = await request.body()
            headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
            try:
                with _httpx.Client(timeout=60.0) as client:
                    resp = client.post(url, content=body, headers=headers)
                return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
            except _httpx.HTTPError as exc:
                raise HTTPException(status_code=503, detail="TTS backend unavailable") from exc

    if _os.environ.get("SERVICETITAN_ENABLED", "false").lower() == "true":
        @app.post(_SERVICETITAN_POLL_PATH)
        def servicetitan_poll() -> dict:
            """Bounded read from ServiceTitan.

            Available only when `SERVICETITAN_ENABLED=true`.
            """
            try:
                from .integrations.servicetitan import ServiceTitanNotConfiguredError, ServiceTitanClient, ServiceTitanSync
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            try:
                client = ServiceTitanClient()
            except ServiceTitanNotConfiguredError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            sync = ServiceTitanSync(client)
            return {
                "results": [
                    {
                        "resource": result.resource,
                        "fetched": result.fetched,
                        "failed": result.failed,
                        "error": result.error,
                    }
                    for result in sync.run()
                ]
            }

    return app


def _backend_from_env() -> Optional[VoiceBackend]:
    """GrokVoiceBackend only if GROK_API_KEY is actually set -- otherwise
    None, so create_app() falls back to NullVoiceBackend. Never silently
    construct a backend that will fail on first real use."""
    import os

    if os.environ.get("GROK_API_KEY"):
        from .workers.angel.voice import GrokVoiceBackend
        return GrokVoiceBackend()
    return None


def _ghl_client_from_env() -> Optional[GHLClient]:
    import os

    if os.environ.get("GHL_API_KEY") and os.environ.get("GHL_LOCATION_ID"):
        from .workers.angel.ghl import GoHighLevelClient
        return GoHighLevelClient()
    return None


def _leo_outreach_enabled_from_env() -> bool:
    """Require an explicit activation flag for automated outbound messaging."""
    return _os.environ.get("LEO_OUTREACH_ENABLED", "").strip().lower() == "true"


def _site_magic_queue_from_env() -> Optional[SiteMagicQueue]:
    """HTTPWebhookSiteMagicQueue only when both webhook env vars are set --
    otherwise None, so create_app() falls back to NullSiteMagicQueue.

    Without this, SITE_MAGIC_WORKER_WEBHOOK_URL can be set in the
    deployment environment and still do nothing: nothing else in the
    process reads it, so an intake would create a `queued` job row that
    no worker is ever told about (exactly what left job
    550e8400-... sitting queued from 2026-08-10 to 2026-08-11).

    SiteMagicNotConfiguredError is caught rather than allowed to
    propagate: this runs at module import, and a partially-configured
    environment must degrade the Site Magic hand-off, not break the
    import of the entire app (which would take down /health and every
    unrelated route on a serverless cold start).
    """
    from .site_magic import SiteMagicNotConfiguredError

    if not (
        _os.environ.get("SITE_MAGIC_WORKER_WEBHOOK_URL")
        and _os.environ.get("SITE_MAGIC_WORKER_WEBHOOK_SECRET")
    ):
        return None
    try:
        from .site_magic_adapters import HTTPWebhookSiteMagicQueue
        return HTTPWebhookSiteMagicQueue()
    except SiteMagicNotConfiguredError:
        return None


def _site_magic_control_build_dispatcher_from_env() -> Optional[SiteMagicBuildDispatcher]:
    """Resolve the standalone control-plane build adapter only when its
    dedicated webhook contract is fully configured.

    This deliberately does not reuse SITE_MAGIC_WORKER_WEBHOOK_URL: that
    endpoint transports legacy site_magic_jobs and is not the product build
    boundary.
    """
    from .site_magic import SiteMagicNotConfiguredError

    if not (
        _os.environ.get("SITE_MAGIC_CONTROL_BUILD_WEBHOOK_URL")
        and _os.environ.get("SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET")
    ):
        return None
    try:
        from .site_magic_adapters import HTTPWebhookSiteMagicBuildDispatcher
        return HTTPWebhookSiteMagicBuildDispatcher()
    except SiteMagicNotConfiguredError:
        return None


def _site_magic_artifact_storage_from_env() -> Optional[ArtifactStorage]:
    """SupabaseArtifactStorage only when both storage env vars are set --
    otherwise None, so create_app() falls back to NullArtifactStorage.

    SITE_MAGIC_STORAGE_SERVICE_KEY is the service-role key, deliberately
    a different var from SUPABASE_PUBLISHABLE_KEY (used for customer
    auth) -- see SupabaseArtifactStorage's docstring. Same
    import-time-safety reasoning as _site_magic_queue_from_env().
    """
    from .site_magic import SiteMagicNotConfiguredError

    if not (
        _os.environ.get("SUPABASE_URL")
        and _os.environ.get("SITE_MAGIC_STORAGE_SERVICE_KEY")
    ):
        return None
    try:
        from .site_magic_adapters import SupabaseArtifactStorage
        return SupabaseArtifactStorage()
    except SiteMagicNotConfiguredError:
        return None


# Default app instance for `uvicorn webstaffr.app:app` (local dev) and for
# the Vercel entrypoint at /index.py (deployed). db_path and backends are
# picked up from environment at process start -- set WEBSTAFFR_DB_PATH,
# DATABASE_URL, GHL_API_KEY/GHL_LOCATION_ID, etc. as Vercel project
# environment variables. This app itself is not containerized -- it
# deploys to Vercel; the repo's Dockerfile builds the separate Site Magic
# Node worker that runs on Railway (it needs a persistent process for
# Playwright/Chromium, which serverless can't provide).
_default_ghl_client = _ghl_client_from_env()

app = create_app(
    db_path=_os.environ.get("WEBSTAFFR_DB_PATH", "webstaffr.db"),
    voice_backend=_backend_from_env(),
    ghl_client=_default_ghl_client,
    ghl_messaging_client=(
        _default_ghl_client if _leo_outreach_enabled_from_env() else None
    ),
    site_magic_queue=_site_magic_queue_from_env(),
    site_magic_artifact_storage=_site_magic_artifact_storage_from_env(),
    retell_verifier=None,  # resolved from RETELL_WEBHOOK_SECRET inside create_retell_router()
    ghl_webhook_verifier=None,  # resolved from GHL_WEBHOOK_SECRET inside create_angel_router()
    book_api_verifier=None,  # resolved from BOOK_API_KEY inside create_angel_router()
    stripe_webhook_verifier=None,  # resolved from STRIPE_WEBHOOK_SECRET inside create_angel_router()
)

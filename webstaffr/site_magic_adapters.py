"""Real (non-Null) implementations of Site Magic's Protocol contracts from
site_magic.py and site_magic_security.py.

Same Protocol + Null* + real-implementation shape as every other
integration in this repo (webstaffr/integrations/design_critique/client.py
is the canonical example): env-driven constructors that raise a
*NotConfiguredError eagerly rather than failing later, silently.

None of these have been run against live credentials or a live worker
endpoint -- see docs/STANDUP_2026-08-09_IMPECCABLE_PHASE_1.md. Unit-tested
against fakes/mocked httpx only.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from .site_magic import ArtifactStorage, SiteCrawler, SiteMagicNotConfiguredError, SiteMagicQueue
from .site_magic_control import SiteMagicBuildDispatcher, SiteMagicBuildRequest
from .site_magic_security import extract_hostile_source_text, normalize_public_url, same_origin

logger = logging.getLogger("webstaffr.site_magic_adapters")


class HTTPWebhookSiteMagicBuildDispatcher:
    """Dispatch an approved control-plane build to a standalone engine.

    This is intentionally separate from ``HTTPWebhookSiteMagicQueue``. The
    legacy queue transports ``site_magic_jobs``; this adapter transports only
    the approved control-plane build envelope.
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        secret: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.webhook_url = webhook_url or os.environ.get("SITE_MAGIC_CONTROL_BUILD_WEBHOOK_URL")
        self.secret = secret or os.environ.get("SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET")
        if not self.webhook_url or not self.secret:
            raise SiteMagicNotConfiguredError(
                "HTTPWebhookSiteMagicBuildDispatcher requires "
                "SITE_MAGIC_CONTROL_BUILD_WEBHOOK_URL and "
                "SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET."
            )
        self._client = httpx.Client(timeout=10.0, transport=transport)

    def dispatch(self, *, build: SiteMagicBuildRequest) -> None:
        try:
            response = self._client.post(
                self.webhook_url,
                json=build.public(),
                headers={"X-Site-Magic-Secret": self.secret},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "site_magic_control_build_dispatch_failed build_id=%s error_type=%s",
                build.build_id, type(exc).__name__,
            )
            raise SiteMagicNotConfiguredError(
                f"Site Magic control build webhook call failed: {exc}"
            ) from exc

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()


class HTTPWebhookSiteMagicQueue:
    """Hands a queued job off to whatever's listening at
    SITE_MAGIC_WORKER_WEBHOOK_URL -- a single authenticated POST, not a
    broker client.

    This repo has no visibility into the actual SMMM/Celery worker
    infrastructure's internal API (that's a separate service), so rather
    than guess its protocol, this defines OUR side of a generic webhook
    contract: POST {job_id, tenant_id} with a shared-secret header,
    matching this codebase's existing SharedSecretVerifier convention
    (webstaffr/workers/angel/api_auth.py) for the receiving end. Whoever
    owns the worker needs to register a listener at that URL that verifies
    the header and pulls the full job via GET /site-magic/jobs/{job_id}.

    Env vars:
      SITE_MAGIC_WORKER_WEBHOOK_URL     required
      SITE_MAGIC_WORKER_WEBHOOK_SECRET  required
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        secret: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.webhook_url = webhook_url or os.environ.get("SITE_MAGIC_WORKER_WEBHOOK_URL")
        self.secret = secret or os.environ.get("SITE_MAGIC_WORKER_WEBHOOK_SECRET")
        if not self.webhook_url or not self.secret:
            raise SiteMagicNotConfiguredError(
                "HTTPWebhookSiteMagicQueue requires SITE_MAGIC_WORKER_WEBHOOK_URL and "
                "SITE_MAGIC_WORKER_WEBHOOK_SECRET (env vars or constructor args)."
            )
        self._client = httpx.Client(timeout=10.0, transport=transport)

    def enqueue(self, *, job_id: str, tenant_id: str) -> None:
        try:
            response = self._client.post(
                self.webhook_url,
                json={"job_id": job_id, "tenant_id": tenant_id},
                headers={"X-Site-Magic-Secret": self.secret},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "site_magic_enqueue_webhook_failed job_id=%s error_type=%s",
                job_id, type(exc).__name__,
            )
            raise SiteMagicNotConfiguredError(f"Site Magic worker webhook call failed: {exc}") from exc

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()


class SupabaseArtifactStorage:
    """Public URL access to the Supabase Storage bucket the Node
    worker seals builds into (see webstaffr/site_magic_adapters.ts's
    SupabaseArtifactStore -- same bucket, same object-path convention:
    `{tenant_id}/{job_id_component}/{build_id}.tar`, but this class is only
    ever given `locator` directly, so it doesn't need to reconstruct it).

    ADR-029: `publish()` returns a public bucket URL (Phase 1 MVP).
    The bucket is configured to be publicly readable via Supabase bucket
    policies. Phase 3+ will add a CDN layer (Cloudflare Workers + R2) for
    custom domain and global caching, but Phase 1 uses direct Supabase
    Storage URLs.

    Env vars:
      SUPABASE_URL                     required
      SITE_MAGIC_STORAGE_SERVICE_KEY   required (service-role key, NOT the
                                        publishable key used elsewhere in
                                        this repo for customer auth)
      SITE_MAGIC_STORAGE_BUCKET        optional, defaults to "site-magic-builds"
    """

    _PREVIEW_TTL_SECONDS = 3600
    _PUBLISHED_TTL_SECONDS = 10 * 365 * 24 * 3600

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_key: Optional[str] = None,
        bucket: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.service_key = service_key or os.environ.get("SITE_MAGIC_STORAGE_SERVICE_KEY")
        if not self.base_url or not self.service_key:
            raise SiteMagicNotConfiguredError(
                "SupabaseArtifactStorage requires SUPABASE_URL and "
                "SITE_MAGIC_STORAGE_SERVICE_KEY (env vars or constructor args)."
            )
        self.bucket = bucket or os.environ.get("SITE_MAGIC_STORAGE_BUCKET", "site-magic-builds")
        self._client = httpx.Client(timeout=15.0, transport=transport)

    def _sign(self, *, locator: str, expires_in: int) -> str:
        try:
            response = self._client.post(
                f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{locator}",
                json={"expiresIn": expires_in},
                headers={
                    "Authorization": f"Bearer {self.service_key}",
                    "apikey": self.service_key,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "site_magic_storage_sign_failed locator=%s error_type=%s",
                locator, type(exc).__name__,
            )
            raise SiteMagicNotConfiguredError(f"Supabase Storage sign call failed: {exc}") from exc

        try:
            signed_path: str = response.json()["signedURL"]
        except (KeyError, ValueError) as exc:
            raise SiteMagicNotConfiguredError(
                f"Supabase Storage sign response missing signedURL: {exc}"
            ) from exc
        return f"{self.base_url}/storage/v1{signed_path}"

    def signed_preview_url(self, *, tenant_id: str, locator: str) -> str:
        return self._sign(locator=locator, expires_in=self._PREVIEW_TTL_SECONDS)

    def publish(self, *, tenant_id: str, locator: str, build_id: str) -> str:
        # ADR-029: Return public bucket URL (Phase 1 MVP)
        # Assumes bucket is configured to be publicly readable via Supabase bucket policies.
        # Phase 3+: Cloudflare Workers + R2 will provide custom domain and CDN.
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{locator}"

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()


class ArtifactStorageSiteMagicPublisher:
    """Adapt the existing artifact store to the control-plane publisher port.

    The control plane owns the explicit release decision. This adapter only
    turns an accepted checkpoint's artifact locator into a public locator; it
    cannot create a release or bypass checkpoint acceptance.
    """

    def __init__(self, storage: ArtifactStorage) -> None:
        self._storage = storage

    def publish(
        self, *, tenant_id: str, checkpoint_id: str, artifact_locator: str,
        artifact_manifest: dict[str, Any],
    ) -> str:
        if not isinstance(artifact_locator, str) or not artifact_locator.strip():
            raise SiteMagicNotConfiguredError("Accepted checkpoint has no publishable artifact locator")
        return self._storage.publish(
            tenant_id=tenant_id, locator=artifact_locator, build_id=checkpoint_id,
        )


class HttpxSiteCrawler:
    """Fetches a `url`-source job's public pages for the Site Magic
    ingestion phase.

    Every crawled page is re-validated through normalize_public_url()
    immediately before the request, on top of the validation already done
    at job-creation time in site_magic_router.py -- necessary because
    ingestion happens later, asynchronously, and a DNS record an attacker
    controls could have been repointed at a private address in between.

    SSRF Protection (ADR-028): Pre-request DNS re-validation (Option B).
    Narrows the validate-then-connect race (millisecond TOCTOU window)
    rather than fully closing it. Connection-level IP pinning (Option A)
    would eliminate TOCTOU entirely but requires custom httpx Transport;
    deferred to Phase 3 if threat model changes. Suitable for MVP tenant-
    website crawling (low-risk, intentional content).

    Same-origin pages only (same_origin() from site_magic_security.py),
    matching the SSRF boundary's "crawl same-origin pages only" rule --
    this fetches the one given URL, not a general spider; multi-page
    ingestion is the caller's job (fetch, extract same-origin links,
    fetch each of those).
    """

    MAX_PAGE_BYTES = 5_000_000
    MAX_REDIRECTS = 3

    def __init__(
        self,
        timeout: float = 15.0,
        transport: Optional[httpx.BaseTransport] = None,
        resolver: Any = None,
    ) -> None:
        # Redirects are followed manually (never by httpx itself) so every
        # hop -- not just the initial URL -- goes through
        # normalize_public_url()'s SSRF validation before it's fetched.
        self._client = httpx.Client(timeout=timeout, follow_redirects=False, transport=transport)
        # resolver threads through to normalize_public_url() -- defaults to
        # its own real socket.getaddrinfo when None; tests inject a fake so
        # they never do a real DNS lookup.
        self._resolve_kwargs = {} if resolver is None else {"resolver": resolver}

    def _validate(self, url: str) -> str:
        return normalize_public_url(url, **self._resolve_kwargs)

    def snapshot(self, *, url: str, tenant_id: str) -> dict[str, Any]:
        original_url = self._validate(url)
        current_url = original_url
        for _ in range(self.MAX_REDIRECTS + 1):
            try:
                response = self._client.get(
                    current_url,
                    headers={"User-Agent": "NetBuildProSiteMagicCrawler/1.0"},
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "site_magic_crawl_failed tenant_id=%s error_type=%s",
                    tenant_id, type(exc).__name__,
                )
                raise SiteMagicNotConfiguredError(f"Crawl of {current_url!r} failed: {exc}") from exc

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SiteMagicNotConfiguredError(f"Crawl of {current_url!r} redirected with no Location")
                current_url = self._validate(str(httpx.URL(current_url).join(location)))
                if not same_origin(original_url, current_url):
                    raise SiteMagicNotConfiguredError(
                        f"Crawl of {original_url!r} redirected off-origin to {current_url!r}"
                    )
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "site_magic_crawl_failed tenant_id=%s error_type=%s",
                    tenant_id, type(exc).__name__,
                )
                raise SiteMagicNotConfiguredError(f"Crawl of {current_url!r} failed: {exc}") from exc
            html = response.text[: self.MAX_PAGE_BYTES]
            return {
                "url": current_url,
                "status_code": response.status_code,
                "text": extract_hostile_source_text(html),
            }

        raise SiteMagicNotConfiguredError(f"Crawl of {original_url!r} exceeded {self.MAX_REDIRECTS} redirects")

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()

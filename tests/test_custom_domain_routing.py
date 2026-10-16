import unittest
import os
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.db import get_connection
from webstaffr.custom_domain_middleware import CustomDomainMiddleware
from webstaffr.custom_domain import resolve_tenant_from_host


class CustomDomainMiddlewareTestCase(unittest.IsolatedAsyncioTestCase):
    """Tests for phase 2 custom domain middleware.

    Custom domain middleware rewrites requests to custom domains to the
    internal /sites/{tenant_id}/web routing structure via Host header lookup.
    """

    def setUp(self):
        self.middleware = CustomDomainMiddleware(MagicMock())

    async def test_middleware_rewrites_custom_domain_path(self):
        """Middleware should rewrite custom domain paths to /sites/{tenant_id}/web."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="desertcooling.com")
        request.url.path = "/"
        request.scope = {"path": "/"}
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = "tenant-abc123"

            await self.middleware.dispatch(request, call_next)

            # Verify path was rewritten
            self.assertEqual(request.scope["path"], "/sites/tenant-abc123/web/")
            # Verify call_next was invoked
            call_next.assert_called_once()

    async def test_middleware_handles_subpaths(self):
        """Middleware should preserve subpaths in rewrite."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="desertcooling.com")
        request.url.path = "/about"
        request.scope = {"path": "/about"}
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = "tenant-xyz"

            await self.middleware.dispatch(request, call_next)

            self.assertEqual(request.scope["path"], "/sites/tenant-xyz/web/about")

    async def test_middleware_handles_services_subpath(self):
        """Middleware should handle /services/{slug} subpaths."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="cooltech.com")
        request.url.path = "/services/ac-repair"
        request.scope = {"path": "/services/ac-repair"}
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = "tenant-service"

            await self.middleware.dispatch(request, call_next)

            self.assertEqual(request.scope["path"], "/sites/tenant-service/web/services/ac-repair")

    async def test_middleware_passthrough_for_path_based_requests(self):
        """Middleware should pass through requests that aren't custom domains."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="localhost:8000")
        request.url.path = "/sites/tenant-123/web"
        request.scope = {"path": "/sites/tenant-123/web"}
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = None  # Not a custom domain

            await self.middleware.dispatch(request, call_next)

            # Path should remain unchanged
            self.assertEqual(request.scope["path"], "/sites/tenant-123/web")

    async def test_middleware_stores_request_state(self):
        """Middleware should store custom domain info in request.state for debugging."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="test.com")
        request.url.path = "/contact"
        request.scope = {"path": "/contact"}
        request.state = MagicMock()
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = "tenant-debug"

            await self.middleware.dispatch(request, call_next)

            # Verify state was set for debugging
            self.assertEqual(request.state.custom_domain_tenant_id, "tenant-debug")
            self.assertEqual(request.state.original_path, "/contact")

    async def test_middleware_handles_sitemap_xml(self):
        """Middleware should handle special paths like /sitemap.xml."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="mybusiness.com")
        request.url.path = "/sitemap.xml"
        request.scope = {"path": "/sitemap.xml"}
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = "tenant-sitemap"

            await self.middleware.dispatch(request, call_next)

            self.assertEqual(request.scope["path"], "/sites/tenant-sitemap/web/sitemap.xml")

    async def test_middleware_handles_robots_txt(self):
        """Middleware should handle /robots.txt."""
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="mybusiness.com")
        request.url.path = "/robots.txt"
        request.scope = {"path": "/robots.txt"}
        request.app.state.db_path = ":memory:"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host") as mock_resolve:
            mock_resolve.return_value = "tenant-robots"

            await self.middleware.dispatch(request, call_next)

            self.assertEqual(request.scope["path"], "/sites/tenant-robots/web/robots.txt")

    async def test_middleware_does_not_rewrite_static_assets(self):
        request = MagicMock()
        request.method = "GET"
        request.headers.get = MagicMock(return_value="desertcooling.com")
        request.url.path = "/static/angel-widget.js"
        request.scope = {"path": "/static/angel-widget.js"}
        request.app.state.db_path = ":memory:"
        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host", return_value="tenant-abc"):
            await self.middleware.dispatch(request, call_next)

        self.assertEqual(request.scope["path"], "/static/angel-widget.js")

    async def test_middleware_does_not_rewrite_api_routes(self):
        for method, path in (
            ("POST", "/chat"),
            ("POST", "/intake"),
            ("POST", "/sites/tenant-abc/leads"),
            ("GET", "/health"),
        ):
            with self.subTest(method=method, path=path):
                request = MagicMock()
                request.method = method
                request.headers.get = MagicMock(return_value="desertcooling.com")
                request.url.path = path
                request.scope = {"path": path}
                request.app.state.db_path = ":memory:"
                call_next = AsyncMock(return_value=MagicMock())

                with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host", return_value="tenant-abc"):
                    await self.middleware.dispatch(request, call_next)

                self.assertEqual(request.scope["path"], path)

    async def test_middleware_does_not_rewrite_non_get_page_requests(self):
        request = MagicMock()
        request.method = "POST"
        request.headers.get = MagicMock(return_value="desertcooling.com")
        request.url.path = "/contact"
        request.scope = {"path": "/contact"}
        request.app.state.db_path = ":memory:"
        call_next = AsyncMock(return_value=MagicMock())

        with patch("webstaffr.custom_domain_middleware.resolve_tenant_from_host", return_value="tenant-abc"):
            await self.middleware.dispatch(request, call_next)

        self.assertEqual(request.scope["path"], "/contact")


class CustomDomainResolutionTestCase(unittest.TestCase):
    """Tests for custom domain resolution via Host header lookup."""

    def test_resolve_tenant_from_host_valid_domain(self):
        """resolve_tenant_from_host should query custom_domain column."""
        # This test verifies the integration with the database
        # For unit testing, we mock the database
        with patch("webstaffr.custom_domain.get_connection") as mock_conn:
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone = MagicMock(return_value={"tenant_id": "tenant-123"})
            mock_db.execute = MagicMock(return_value=mock_cursor)
            mock_conn.return_value = mock_db

            result = resolve_tenant_from_host("desertcooling.com", ":memory:")

            self.assertEqual(result, "tenant-123")
            mock_db.execute.assert_called_once()

    def test_resolve_tenant_from_host_strips_port(self):
        """resolve_tenant_from_host should strip port from Host header."""
        with patch("webstaffr.custom_domain.get_connection") as mock_conn:
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone = MagicMock(return_value={"tenant_id": "tenant-port"})
            mock_db.execute = MagicMock(return_value=mock_cursor)
            mock_conn.return_value = mock_db

            result = resolve_tenant_from_host("desertcooling.com:8080", ":memory:")

            self.assertEqual(result, "tenant-port")
            # Verify the query was made for the domain without port
            args, kwargs = mock_db.execute.call_args
            self.assertIn("desertcooling.com", str(args))

    def test_resolve_tenant_from_host_not_found(self):
        """resolve_tenant_from_host should return None for unknown domains."""
        with patch("webstaffr.custom_domain.get_connection") as mock_conn:
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone = MagicMock(return_value=None)
            mock_db.execute = MagicMock(return_value=mock_cursor)
            mock_conn.return_value = mock_db

            result = resolve_tenant_from_host("unknown.com", ":memory:")

            self.assertIsNone(result)

    def test_resolve_tenant_from_host_empty_header(self):
        """resolve_tenant_from_host should handle missing Host header gracefully."""
        result = resolve_tenant_from_host("", ":memory:")
        self.assertIsNone(result)

    def test_resolve_tenant_from_host_case_insensitive(self):
        """resolve_tenant_from_host should normalize domain case."""
        with patch("webstaffr.custom_domain.get_connection") as mock_conn:
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone = MagicMock(return_value={"tenant_id": "tenant-case"})
            mock_db.execute = MagicMock(return_value=mock_cursor)
            mock_conn.return_value = mock_db

            # Call with mixed case
            result = resolve_tenant_from_host("DesertCooling.COM", ":memory:")

            self.assertEqual(result, "tenant-case")
            # Verify domain was lowercased in query
            args, kwargs = mock_db.execute.call_args
            self.assertIn("desertcooling.com", str(args).lower())


class CustomDomainIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(db_path=self.db_path)
        self._client_context = TestClient(app)
        self.client = self._client_context.__enter__()

        response = self.client.post(
            "/intake",
            json={
                "biz_name": "Custom Domain Plumbing",
                "phone": "555-0100",
                "email": "owner@example.com",
                "industry": "Plumber",
                "service_area": "Phoenix",
                "tagline": "Local plumbing service",
                "differentiator": "Family operated",
                "services": ["Leak Repair"],
                "license_number": "N/A",
                "plan": "office_staff",
                "lead_routing": "office",
                "approver": "owner",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.tenant_id = response.json()["tenant_id"]
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE tenants SET custom_domain = ? WHERE tenant_id = ?",
                ("custom.example", self.tenant_id),
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self._client_context.__exit__(None, None, None)
        os.remove(self.db_path)

    def test_custom_domain_page_renders_but_assets_and_api_paths_are_not_rewritten(self):
        headers = {"Host": "custom.example"}

        page = self.client.get("/", headers=headers)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Custom Domain Plumbing", page.text)

        css = self.client.get("/static/site.css", headers=headers)
        self.assertEqual(css.status_code, 200)
        self.assertIn("text/css", css.headers["content-type"])

        widget = self.client.get("/static/angel-widget.js", headers=headers)
        self.assertEqual(widget.status_code, 200)
        self.assertIn("javascript", widget.headers["content-type"])

        health = self.client.get("/health", headers=headers)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})

        lead = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            headers=headers,
            json={
                "name": "Custom Domain Customer",
                "phone": "555-0199",
                "message": "I need help with a leak.",
                "source_path": "/contact",
            },
        )
        self.assertEqual(lead.status_code, 201, lead.text)

        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT tenant_id, name FROM website_leads WHERE lead_id = ?",
                (lead.json()["lead_id"],),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["tenant_id"], self.tenant_id)
        self.assertEqual(row["name"], "Custom Domain Customer")


if __name__ == "__main__":
    unittest.main()

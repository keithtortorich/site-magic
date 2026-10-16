import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app


class SecurityMiddlewareTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(db_path=self.db_path, max_request_body_bytes=128)
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def test_security_headers_cover_success_responses(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "strict-origin-when-cross-origin")
        self.assertEqual(
            response.headers["permissions-policy"],
            "camera=(), microphone=(), geolocation=()",
        )

    def test_security_headers_cover_error_responses(self):
        response = self.client.get("/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_oversized_request_is_rejected(self):
        response = self.client.post(
            "/chat",
            content=b"x" * 129,
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "Request body too large"})
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_request_at_limit_reaches_route_validation(self):
        response = self.client.post(
            "/chat",
            content=b"x" * 128,
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)

    def test_hsts_is_added_for_https(self):
        app = create_app(db_path=self.db_path)
        with TestClient(app, base_url="https://testserver") as client:
            response = client.get("/health")
        self.assertEqual(
            response.headers["strict-transport-security"],
            "max-age=31536000; includeSubDomains",
        )

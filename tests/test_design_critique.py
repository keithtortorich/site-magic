"""Tests for the on-demand OpenRouter design-critique integration."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx

from webstaffr.integrations.design_critique.client import (
    DesignCritiqueError,
    DesignCritiqueNotConfiguredError,
    NullDesignCritiqueClient,
    OpenRouterDesignCritiqueClient,
)


class NullDesignCritiqueClientTestCase(unittest.TestCase):
    def test_never_calls_network_and_names_the_page(self) -> None:
        client = NullDesignCritiqueClient()
        result = client.critique("<html></html>", page_label="about")
        self.assertIn("about", result)
        self.assertIn("not configured", result.lower())


class OpenRouterClientConstructionTestCase(unittest.TestCase):
    def test_raises_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(DesignCritiqueNotConfiguredError):
                OpenRouterDesignCritiqueClient()

    def test_constructs_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"OPENROUTER_API_KEY": "sk-or-test", "DESIGN_CRITIQUE_MODEL": "some/model"},
            clear=True,
        ):
            client = OpenRouterDesignCritiqueClient()
        self.assertEqual(client.api_key, "sk-or-test")
        self.assertEqual(client.model, "some/model")

    def test_constructor_args_override_env(self) -> None:
        client = OpenRouterDesignCritiqueClient(api_key="explicit-key", model="explicit/model")
        self.assertEqual(client.api_key, "explicit-key")
        self.assertEqual(client.model, "explicit/model")

    def test_defaults_to_cheap_model_when_unset(self) -> None:
        client = OpenRouterDesignCritiqueClient(api_key="k")
        self.assertTrue(client.model)  # some default is always set
        self.assertNotEqual(client.model, "")


class OpenRouterClientCritiqueTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OpenRouterDesignCritiqueClient(api_key="test-key", model="test/model")

    def test_successful_critique_returns_content(self) -> None:
        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {
            "choices": [{"message": {"content": "  Solid hierarchy, tighten the hero spacing.  "}}]
        }
        with patch.object(self.client.client, "post", return_value=fake_response) as mock_post:
            result = self.client.critique("<html><h1>Hi</h1></html>", page_label="home")

        self.assertEqual(result, "Solid hierarchy, tighten the hero spacing.")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["model"], "test/model")
        self.assertIn("home", kwargs["json"]["messages"][1]["content"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")

    def test_http_error_raises_design_critique_error(self) -> None:
        with patch.object(
            self.client.client, "post", side_effect=httpx.ConnectError("boom")
        ):
            with self.assertRaises(DesignCritiqueError):
                self.client.critique("<html></html>")

    def test_non_2xx_raises_design_critique_error(self) -> None:
        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        with patch.object(self.client.client, "post", return_value=fake_response):
            with self.assertRaises(DesignCritiqueError):
                self.client.critique("<html></html>")

    def test_unparseable_response_raises_design_critique_error(self) -> None:
        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {"unexpected": "shape"}
        with patch.object(self.client.client, "post", return_value=fake_response):
            with self.assertRaises(DesignCritiqueError):
                self.client.critique("<html></html>")

    def test_never_asks_for_accessibility_feedback(self) -> None:
        # The mechanical a11y checker already owns this ground (see
        # webstaffr/site_a11y_check.py) -- the critique prompt must not
        # duplicate it, so this guards against the system prompt drifting.
        from webstaffr.integrations.design_critique.client import _SYSTEM_PROMPT

        self.assertIn("accessibility", _SYSTEM_PROMPT.lower())
        self.assertIn("already checked separately", _SYSTEM_PROMPT.lower())


if __name__ == "__main__":
    unittest.main()

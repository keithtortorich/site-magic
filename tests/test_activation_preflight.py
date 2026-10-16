from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.activation_preflight import MVP_REQUIRED_ENV, main, run_preflight


def _configured_env():
    return {name: f"private-{name.lower()}-value" for name in MVP_REQUIRED_ENV}


class TestActivationPreflight(unittest.TestCase):
    def test_all_mvp_configuration_present_and_outreach_off_passes(self):
        env = _configured_env()
        env["LEO_OUTREACH_ENABLED"] = "false"

        results = run_preflight(env)

        self.assertTrue(all(result.passed for result in results), results)
        self.assertEqual(results[-1].name, "LEO_OUTREACH_DISABLED")

    def test_every_required_name_fails_closed_when_missing(self):
        for missing in MVP_REQUIRED_ENV:
            with self.subTest(missing=missing):
                env = _configured_env()
                env.pop(missing)
                results = run_preflight(env)
                result = next(item for item in results if item.name == missing)
                self.assertFalse(result.passed)

    def test_leo_outreach_true_fails_mvp_preflight(self):
        env = _configured_env()
        env["LEO_OUTREACH_ENABLED"] = "true"

        result = run_preflight(env)[-1]

        self.assertFalse(result.passed)
        self.assertNotIn(env["GHL_API_KEY"], result.detail)

    def test_json_output_contains_names_and_statuses_but_no_values(self):
        env = _configured_env()
        output = io.StringIO()
        with patch.dict("os.environ", env, clear=True), redirect_stdout(output):
            exit_code = main(["--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(len(payload), len(MVP_REQUIRED_ENV) + 1)
        rendered = output.getvalue()
        for value in env.values():
            self.assertNotIn(value, rendered)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "discover_searxng.py"
SPEC = importlib.util.spec_from_file_location("discover_searxng", MODULE_PATH)
DISCOVERY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DISCOVERY)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"results": [{"title": "Demo result", "url": "https://example.invalid", "engines": ["google"]}]}).encode()


class SearXNGDiscoveryTests(unittest.TestCase):
    def test_results_are_explicitly_non_authoritative(self):
        with patch.object(DISCOVERY.urllib.request, "urlopen", return_value=FakeResponse()):
            value = DISCOVERY.discover("http://127.0.0.1:8080", ["HVAC contractor Phoenix"])
        self.assertFalse(value["authoritative"])
        self.assertFalse(value["selectionEligible"])
        self.assertEqual(value["results"][0]["url"], "https://example.invalid")


if __name__ == "__main__":
    unittest.main()

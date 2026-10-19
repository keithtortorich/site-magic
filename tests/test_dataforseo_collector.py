import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "collect_dataforseo_serp.py"
SPEC = importlib.util.spec_from_file_location("collect_dataforseo_serp", MODULE_PATH)
COLLECTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(COLLECTOR)


class DataForSeoCollectorTests(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        old_login = COLLECTOR.os.environ.pop("DATAFORSEO_LOGIN", None)
        old_password = COLLECTOR.os.environ.pop("DATAFORSEO_PASSWORD", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "DATAFORSEO_LOGIN"):
                COLLECTOR.required_env("DATAFORSEO_LOGIN")
        finally:
            if old_login is not None:
                COLLECTOR.os.environ["DATAFORSEO_LOGIN"] = old_login
            if old_password is not None:
                COLLECTOR.os.environ["DATAFORSEO_PASSWORD"] = old_password

    def test_extracts_only_ranked_organic_items(self):
        response = {
            "tasks": [{
                "status_code": 20000,
                "result": [{"items": [
                    {"type": "organic", "rank_absolute": 3, "url": "https://demo.example.invalid/"},
                    {"type": "local_pack", "rank_absolute": 1, "url": "https://maps.example.invalid/"},
                    {"type": "organic", "rank_absolute": None, "url": "https://missing.example.invalid/"},
                ]}],
            }],
        }
        values = COLLECTOR.extract_observations(
            response,
            metro="phoenix",
            location_code="123",
            query_family="hvac-contractor",
            device="desktop",
        )
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["organicPosition"], 3)
        self.assertEqual(values[0]["provider"], "dataforseo")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_demo_artifacts.py"
SPEC = importlib.util.spec_from_file_location("validate_demo_artifacts", MODULE_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


class VREDemoArtifactTests(unittest.TestCase):
    def setUp(self):
        self.facts_a = json.loads((ROOT / "demo/facts/demo-hvac-a.json").read_text())
        self.facts_b = json.loads((ROOT / "demo/facts/demo-hvac-b.json").read_text())
        self.spec_a = json.loads((ROOT / "demo/site-specs/demo-hvac-a.json").read_text())
        self.spec_b = json.loads((ROOT / "demo/site-specs/demo-hvac-b.json").read_text())

    def test_synthetic_fact_packs_are_valid_and_distinct(self):
        errors = []
        tenant_a = VALIDATOR.validate_facts(self.facts_a, errors)
        tenant_b = VALIDATOR.validate_facts(self.facts_b, errors)
        self.assertEqual(errors, [])
        self.assertEqual({tenant_a, tenant_b}, {"demo-hvac-a", "demo-hvac-b"})
        self.assertNotEqual(VALIDATOR.synthetic_hash(self.facts_a), VALIDATOR.synthetic_hash(self.facts_b))

    def test_site_specs_bind_to_their_own_fact_snapshot(self):
        errors = []
        VALIDATOR.validate_site_spec(self.spec_a, self.facts_a, errors)
        VALIDATOR.validate_site_spec(self.spec_b, self.facts_b, errors)
        self.assertEqual(errors, [])

    def test_cross_tenant_fact_snapshot_is_rejected(self):
        errors = []
        VALIDATOR.validate_site_spec(self.spec_a, self.facts_b, errors)
        self.assertTrue(any("tenantId" in error or "factSnapshotHash" in error for error in errors))

    def test_supported_claim_without_fact_is_rejected(self):
        broken = json.loads(json.dumps(self.spec_a))
        broken["sections"][0]["claims"][0]["factIds"] = []
        errors = []
        VALIDATOR.validate_site_spec(broken, self.facts_a, errors)
        self.assertTrue(any("supported claims require factIds" in error for error in errors))

    def test_model_observation_must_not_be_fact(self):
        analysis = {
            "schemaVersion": "1.0.0",
            "analysisId": "gemini-demo",
            "worker": "gemini-visual",
            "scope": {"inputType": "synthetic-preview", "sourceRefs": ["shot-1"], "tenantMode": "synthetic-demo"},
            "findings": [{
                "findingId": "finding-1",
                "category": "layout",
                "observation": "The CTA is visible in the first viewport.",
                "recommendation": None,
                "evidenceRefs": ["shot-1"],
                "confidence": "high",
                "factual": False,
            }],
        }
        errors = []
        VALIDATOR.validate_model_analysis(analysis, errors)
        self.assertEqual(errors, [])
        analysis["findings"][0]["factual"] = True
        errors = []
        VALIDATOR.validate_model_analysis(analysis, errors)
        self.assertTrue(any("never facts" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

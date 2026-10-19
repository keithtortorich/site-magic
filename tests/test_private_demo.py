import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_private_demo import run


class PrivateDemoHarnessTests(unittest.TestCase):
    def test_runs_both_synthetic_tenants_to_private_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(str(Path(directory) / "demo.db"))
        self.assertEqual(result["release"], "not_requested")
        self.assertEqual(result["isolation"], "cross-tenant reads and build source denied")
        self.assertEqual(result["idempotency"], "duplicate preview callback replayed")
        self.assertTrue(result["quality_gate"])
        self.assertEqual(set(result["tenants"]), {"demo-hvac-a", "demo-hvac-b"})
        for tenant in result["tenants"].values():
            self.assertEqual(tenant["preview"], "ready")
            self.assertEqual(tenant["revised_preview"], "ready")
            self.assertEqual(tenant["plan_versions"], 2)

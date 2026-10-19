import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "select_corpus.py"
SPEC = importlib.util.spec_from_file_location("select_corpus", MODULE_PATH)
SELECTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SELECTOR)


def raw_corpus():
    candidates = []
    for index, (candidate_id, metro) in enumerate((
        ("a-example-com", "phoenix"),
        ("b-example-com", "chicago"),
        ("c-example-com", "dallas_fort_worth"),
    )):
        candidates.append({
            "candidateId": candidate_id,
            "domain": candidate_id.replace("-", "."),
            "companyName": "Unclassified public SERP candidate",
            "metro": metro,
            "franchiseControl": False,
            "serpCollection": [{"organicPosition": index + 1}],
            "classification": "excluded",
            "split": "excluded",
            "exclusion": {"reason": "insufficient-evidence", "evidenceRefs": [candidate_id]},
        })
    return {"surveyRunId": "raw", "candidates": candidates}


class CorpusSelectionTests(unittest.TestCase):
    def test_requires_every_candidate_to_be_explicitly_partitioned(self):
        with self.assertRaisesRegex(ValueError, "partition every raw candidate"):
            SELECTOR.select(raw_corpus(), {"training": ["a-example-com"]})

    def test_assigns_explicit_splits_and_controls(self):
        selected = SELECTOR.select(raw_corpus(), {
            "training": ["a-example-com"],
            "holdout": ["b-example-com"],
            "franchise": ["c-example-com"],
            "excluded": [],
        })
        by_id = {candidate["candidateId"]: candidate for candidate in selected["candidates"]}
        self.assertEqual(by_id["a-example-com"]["classification"], "independent")
        self.assertEqual(by_id["a-example-com"]["split"], "training")
        self.assertEqual(by_id["b-example-com"]["split"], "holdout")
        self.assertEqual(by_id["c-example-com"]["classification"], "franchise")
        self.assertTrue(by_id["c-example-com"]["franchiseControl"])

    def test_exclusion_requires_reason_and_evidence(self):
        with self.assertRaisesRegex(ValueError, "exclusion"):
            SELECTOR.select(raw_corpus(), {
                "training": ["a-example-com"],
                "holdout": [],
                "franchise": [],
                "excluded": ["b-example-com", "c-example-com"],
                "exclusions": {"b-example-com": {"reason": "directory", "evidenceRefs": []}},
            })


if __name__ == "__main__":
    unittest.main()

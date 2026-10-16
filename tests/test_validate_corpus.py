import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_corpus.py"
SPEC = importlib.util.spec_from_file_location("validate_corpus", MODULE_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


METROS = ["phoenix", "chicago", "dallas_fort_worth"]


def make_corpus():
    now = datetime.now(timezone.utc).isoformat()
    corpus = {
        "schemaVersion": "1.0.0",
        "surveyRunId": "hvac-survey-test",
        "generatedAt": now,
        "metros": METROS,
        "queryFamilies": ["hvac-contractor", "ac-repair", "furnace-repair", "emergency-hvac"],
        "crawlPolicy": {
            "robotsTxtRequired": True,
            "delayMs": 2000,
            "concurrency": 2,
            "screenshotsOutsideProductRepo": True,
        },
        "selectionPolicy": {
            "minimumIndependentSites": 12,
            "maximumIndependentSites": 15,
            "minimumIndependentSitesPerMetro": 4,
            "maximumIndependentSitesPerMetro": 5,
            "holdoutSiteCount": 3,
            "holdoutMustIncludeEachMetro": True,
            "paidPlacementsExcluded": True,
            "directoriesExcluded": True,
            "aggregatorsExcluded": True,
            "duplicatesExcluded": True,
            "franchisesAreControlsOnly": True,
        },
        "candidates": [],
    }
    for metro in METROS:
        for index in range(4):
            candidate_id = f"{metro}-{index + 1}"
            corpus["candidates"].append(
                {
                    "candidateId": candidate_id,
                    "domain": f"{candidate_id}.example.com",
                    "companyName": "HVAC Co",
                    "metro": metro,
                    "franchiseControl": False,
                    "serpCollection": [
                        {
                            "provider": "serpapi",
                            "locationCode": metro,
                            "locationName": metro,
                            "device": "desktop",
                            "language": "en-US",
                            "query": f"HVAC contractor {metro}",
                            "observedAt": now,
                            "organicPosition": index + 1,
                            "resultType": "organic",
                            "resultUrl": f"https://{candidate_id}.example.com",
                        }
                    ],
                    "classification": "independent",
                    "split": "holdout" if index == 0 else "training",
                }
            )
    return corpus


class CorpusValidatorTests(unittest.TestCase):
    def validate(self, corpus):
        errors = []
        VALIDATOR.validate_corpus(corpus, errors)
        return errors

    def test_valid_three_metro_split(self):
        self.assertEqual(self.validate(make_corpus()), [])

    def test_holdout_must_cover_each_metro(self):
        corpus = make_corpus()
        corpus["candidates"][4]["split"] = "training"
        errors = self.validate(corpus)
        self.assertTrue(any("holdout must include each metro" in error for error in errors))

    def test_franchise_cannot_enter_training(self):
        corpus = make_corpus()
        candidate = corpus["candidates"][0]
        candidate["classification"] = "franchise"
        candidate["franchiseControl"] = True
        errors = self.validate(corpus)
        self.assertTrue(any("franchise controls cannot enter training or holdout" in error for error in errors))

    def test_selected_site_requires_organic_position(self):
        corpus = make_corpus()
        observation = corpus["candidates"][1]["serpCollection"][0]
        observation["resultType"] = "local-pack"
        observation["organicPosition"] = None
        errors = self.validate(corpus)
        self.assertTrue(any("needs an organic SERP observation" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

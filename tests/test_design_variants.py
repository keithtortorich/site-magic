import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
VALID_IDS = {"workshop-contrast", "field-notebook", "after-hours"}


def test_trade_design_catalog_has_three_provenanced_variants():
    catalog = json.loads((ROOT / "schemas/design-variant-catalog.json").read_text())
    variants = catalog["variants"]
    assert {variant["id"] for variant in variants} == VALID_IDS
    assert len(variants) == 3
    for variant in variants:
        assert variant["provenance"]["source"] == "OriginKit-inspired recreation"
        assert set(variant["tokens"]) == {"ink", "surface", "accent", "support"}
        assert all(len(variant["tokens"][key]) == 7 for key in variant["tokens"])


def test_demo_specs_select_known_design_variants():
    for path in (ROOT / "demo/site-specs").glob("*.json"):
        spec = json.loads(path.read_text())
        assert spec["designVariant"] in VALID_IDS

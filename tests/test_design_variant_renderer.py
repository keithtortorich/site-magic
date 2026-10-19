from webstaffr.design_variants import resolve_design_variant
from webstaffr.site_schema import SiteSchema


def test_trade_defaults_are_deterministic():
    assert resolve_design_variant(None, "HVAC") == "workshop-contrast"
    assert resolve_design_variant(None, "Plumber") == "after-hours"
    assert resolve_design_variant(None, "Landscaping") == "field-notebook"


def test_explicit_unknown_variant_falls_back_safely():
    assert resolve_design_variant("not-a-variant", "HVAC") == "workshop-contrast"


def test_schema_exposes_resolved_variant_and_tokens():
    schema = SiteSchema(
        tenant_id="demo", biz_name="Demo", phone="555", email="demo@example.invalid",
        industry="Plumber", service_area="Demo", tagline="Help", differentiator="Care",
        services=["Repair"], plan="office_staff",
    )
    assert schema.resolved_design_variant == "after-hours"
    assert schema.to_dict()["design_variant"] is None

from datetime import date

import pytest

from webstaffr.seo_content_pipeline import (
    BusinessSEOContext,
    KeywordMetric,
    NullKeywordMetricsProvider,
    NullSearchPerformanceProvider,
    NullSerpIntelligenceProvider,
    FAQ,
    SEOProviderNotConfiguredError,
    SEOArticle,
    SEOContentValidationError,
    SearchPerformance,
    SerpFinding,
    build_answer_first_brief,
    build_schema_graph,
    build_keyword_clusters,
    keyword_priority_score,
    map_internal_links,
    plan_refreshes,
    rank_keyword_metrics,
    render_seo_article_page,
    should_refresh,
)


def _payload():
    business = BusinessSEOContext(
        name="Metro HVAC",
        url="https://example.com",
        phone="(800) 555-0199",
        service_areas=("Tampa", "St. Petersburg"),
        industry="HVAC",
    )
    article = SEOArticle(
        title="Emergency AC Repair in Tampa",
        description="Emergency AC repair information for Tampa homeowners.",
        url="https://example.com/emergency-ac-repair",
        date_published=date(2026, 8, 1),
        direct_answer="Call a qualified local technician if your system stops cooling safely.",
        subtitle="What to check and when to request service.",
        sections=(("Why an AC stops cooling", "Common causes include restricted airflow and electrical faults."),),
        faqs=(FAQ("Do you serve Tampa?", "Yes, Tampa is within our submitted service area."),),
    )
    return business, article


def test_keyword_priority_score_and_refresh_threshold():
    assert keyword_priority_score(1000, 1.5, 50) == 30
    assert should_refresh(1000, 849) is True
    assert should_refresh(1000, 850) is False


def test_schema_graph_contains_only_submitted_optional_values():
    business, article = _payload()
    graph = build_schema_graph(business, article)["@graph"]
    assert graph[0]["@type"] == "HVACBusiness"
    assert "priceRange" not in graph[0]
    assert graph[1]["@type"] == "Article"
    assert graph[2]["@type"] == "FAQPage"


def test_faq_schema_is_omitted_when_no_faqs_exist():
    business, article = _payload()
    article = SEOArticle(**{**article.__dict__, "faqs": ()})
    types = [node["@type"] for node in build_schema_graph(business, article)["@graph"]]
    assert types == ["HVACBusiness", "Article"]


def test_rendered_page_is_mobile_first_and_escapes_tenant_content():
    business, article = _payload()
    article = SEOArticle(**{**article.__dict__, "title": '<script>alert("x")</script>'})
    output = render_seo_article_page(business, article)
    assert '<meta name="viewport"' in output
    assert 'href="tel:8005550199"' in output
    assert '<script>alert("x")</script>' not in output
    assert "&lt;script&gt;" in output


def test_invalid_or_empty_page_data_is_rejected():
    business, article = _payload()
    bad_business = BusinessSEOContext("Metro HVAC", "javascript:alert(1)", "555", ("Tampa",))
    with pytest.raises(SEOContentValidationError):
        render_seo_article_page(bad_business, article)
    with pytest.raises(ValueError):
        keyword_priority_score(100, 1, 0)


def test_keyword_clusters_use_only_intake_services_and_areas():
    emergency, replacement = build_keyword_clusters(
        "HVAC", ("AC repair", "Heat pump installation"), ("Tampa",)
    )
    assert "ac repair tampa" in emergency.keywords
    assert "heat pump installation tampa" in replacement.keywords
    assert "emergency hvac tampa" in emergency.keywords


def test_metrics_are_ranked_by_pipeline_formula():
    ranked = rank_keyword_metrics(
        (
            KeywordMetric("hard", 1000, 1, 100),
            KeywordMetric("winner", 500, 2, 20),
        )
    )
    assert [item.keyword for item in ranked] == ["winner", "hard"]


def test_answer_first_brief_preserves_findings_without_inventing_triggers():
    brief = build_answer_first_brief(
        "Metro HVAC",
        "Tampa",
        SerpFinding("emergency ac repair tampa", ("Common AC failures",), ("capacitor",)),
        verified_conversion_triggers=("24/7 service",),
    )
    assert brief.headings == ("Common AC failures",)
    assert brief.conversion_triggers == ("24/7 service",)
    assert "Do not invent" in brief.direct_answer_instruction


def test_internal_links_are_bidirectional():
    links = map_internal_links("hvac-services", ("ac-repair", "heat-pumps"))
    assert len(links) == 4
    assert links[0].source_slug == "hvac-services"
    assert links[1].target_slug == "hvac-services"


def test_refresh_plan_contains_only_greater_than_15_percent_drops():
    assert plan_refreshes(
        (
            SearchPerformance("refresh", 1000, 840),
            SearchPerformance("hold", 1000, 850),
            SearchPerformance("growth", 1000, 1200),
        )
    ) == ("refresh",)


def test_null_external_providers_fail_explicitly():
    calls = (
        lambda: NullKeywordMetricsProvider().metrics_for(("ac repair",), "Tampa"),
        lambda: NullSerpIntelligenceProvider().analyze("ac repair", "Tampa"),
        lambda: NullSearchPerformanceProvider().performance_for("https://example.com"),
    )
    for call in calls:
        with pytest.raises(SEOProviderNotConfiguredError):
            call()

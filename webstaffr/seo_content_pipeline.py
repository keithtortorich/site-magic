"""Safe local core for WebStaffr's home-services SEO content pipeline.

This module implements the deterministic parts of the founder-provided
four-phase automation: keyword priority scoring, refresh triggering, and
Phase 3 semantic page/schema assembly. Keyword-volume, SERP, and Search
Console acquisition remain injected vendor concerns and do not belong in
the renderer.

All customer-facing facts must be supplied by the tenant. The generator
does not invent pricing, arrival times, availability, certifications, or
reviews.
"""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional, Protocol, Sequence
from urllib.parse import urlparse


class SEOContentValidationError(ValueError):
    """Raised when a page would be unsafe, misleading, or malformed."""


class SEOProviderNotConfiguredError(RuntimeError):
    """Raised when an external SEO data adapter has not been configured."""


@dataclass(frozen=True)
class KeywordMetric:
    keyword: str
    search_volume: float
    commercial_intent_weight: float
    keyword_difficulty: float

    @property
    def priority_score(self) -> float:
        return keyword_priority_score(
            self.search_volume,
            self.commercial_intent_weight,
            self.keyword_difficulty,
        )


class KeywordMetricsProvider(Protocol):
    def metrics_for(self, keywords: Sequence[str], location: str) -> Sequence[KeywordMetric]: ...


class NullKeywordMetricsProvider:
    """Safe default that makes missing external keyword data explicit."""

    def metrics_for(self, keywords: Sequence[str], location: str) -> Sequence[KeywordMetric]:
        raise SEOProviderNotConfiguredError("keyword metrics provider is not configured")


@dataclass(frozen=True)
class SerpFinding:
    keyword: str
    headings: tuple[str, ...]
    missing_entities: tuple[str, ...] = field(default_factory=tuple)
    local_context: tuple[str, ...] = field(default_factory=tuple)


class SerpIntelligenceProvider(Protocol):
    def analyze(self, keyword: str, location: str) -> SerpFinding: ...


class NullSerpIntelligenceProvider:
    """Safe default used until a SERP vendor has been approved."""

    def analyze(self, keyword: str, location: str) -> SerpFinding:
        raise SEOProviderNotConfiguredError("SERP intelligence provider is not configured")


@dataclass(frozen=True)
class SearchPerformance:
    keyword: str
    previous_impressions: int
    current_impressions: int


class SearchPerformanceProvider(Protocol):
    def performance_for(self, site_url: str) -> Sequence[SearchPerformance]: ...


class NullSearchPerformanceProvider:
    """Safe default used until Search Console authorization exists."""

    def performance_for(self, site_url: str) -> Sequence[SearchPerformance]:
        raise SEOProviderNotConfiguredError("search performance provider is not configured")


@dataclass(frozen=True)
class KeywordCluster:
    name: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class ContentBrief:
    primary_keyword: str
    title: str
    headings: tuple[str, ...]
    direct_answer_instruction: str
    conversion_triggers: tuple[str, ...]
    entities: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class InternalLink:
    source_slug: str
    target_slug: str
    anchor_text: str


def keyword_priority_score(
    search_volume: float,
    commercial_intent_weight: float,
    keyword_difficulty: float,
) -> float:
    """Return the pipeline's volume × intent ÷ difficulty priority score."""
    values = (search_volume, commercial_intent_weight, keyword_difficulty)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("keyword score inputs must be finite")
    if search_volume < 0 or commercial_intent_weight < 0:
        raise ValueError("volume and intent weight cannot be negative")
    if keyword_difficulty <= 0:
        raise ValueError("keyword difficulty must be greater than zero")
    return search_volume * commercial_intent_weight / keyword_difficulty


def should_refresh(previous_impressions: int, current_impressions: int) -> bool:
    """Trigger a refresh when impressions fall by more than 15% in 30 days."""
    if previous_impressions < 0 or current_impressions < 0:
        raise ValueError("impressions cannot be negative")
    if previous_impressions == 0:
        return False
    drop = (previous_impressions - current_impressions) / previous_impressions
    return drop > 0.15


_EMERGENCY_MODIFIERS = (
    "emergency",
    "not working",
    "repair",
    "same day",
    "near me",
)
_REPLACEMENT_MODIFIERS = (
    "installation",
    "replacement",
    "cost",
    "vs",
    "review",
)


def build_keyword_clusters(
    industry: str,
    services: Iterable[str],
    service_areas: Iterable[str],
) -> tuple[KeywordCluster, KeywordCluster]:
    """Create factual emergency and replacement silos from intake data."""
    trade = _require_text("industry", industry).lower()
    clean_services = tuple(dict.fromkeys(service.strip() for service in services if service.strip()))
    clean_areas = tuple(dict.fromkeys(area.strip() for area in service_areas if area.strip()))
    if not clean_services:
        raise SEOContentValidationError("at least one service is required")
    if not clean_areas:
        raise SEOContentValidationError("at least one service area is required")

    emergency: list[str] = []
    replacement: list[str] = []
    for area in clean_areas:
        for service in clean_services:
            normalized = service.lower()
            target = replacement if any(term in normalized for term in _REPLACEMENT_MODIFIERS) else emergency
            target.append(f"{normalized} {area.lower()}")
        emergency.extend((f"emergency {trade} {area.lower()}", f"{trade} repair near me"))
        replacement.extend((f"{trade} installation {area.lower()}", f"{trade} replacement cost {area.lower()}"))

    return (
        KeywordCluster("emergency", tuple(dict.fromkeys(emergency))),
        KeywordCluster("replacement", tuple(dict.fromkeys(replacement))),
    )


def rank_keyword_metrics(metrics: Iterable[KeywordMetric]) -> list[KeywordMetric]:
    """Rank keyword metrics highest priority first with stable keyword tie-breaking."""
    return sorted(metrics, key=lambda metric: (-metric.priority_score, metric.keyword.lower()))


def build_answer_first_brief(
    business_name: str,
    service_area: str,
    finding: SerpFinding,
    *,
    verified_conversion_triggers: Iterable[str] = (),
) -> ContentBrief:
    """Turn provider findings into a factual brief without generating claims."""
    name = _require_text("business name", business_name)
    area = _require_text("service area", service_area)
    keyword = _require_text("SERP keyword", finding.keyword)
    headings = tuple(dict.fromkeys(heading.strip() for heading in finding.headings if heading.strip()))
    if not headings:
        headings = (f"About {keyword}", f"Service from {name} in {area}", "Frequently asked questions")
    triggers = tuple(dict.fromkeys(trigger.strip() for trigger in verified_conversion_triggers if trigger.strip()))
    return ContentBrief(
        primary_keyword=keyword,
        title=f"{keyword.title()} | {name}",
        headings=headings,
        direct_answer_instruction=(
            "Write one concise answer of no more than 40 words using only verified tenant facts. "
            "Do not invent prices, guarantees, availability, credentials, or arrival times."
        ),
        conversion_triggers=triggers,
        entities=tuple(dict.fromkeys(finding.missing_entities)),
    )


def map_internal_links(pillar_slug: str, article_slugs: Iterable[str]) -> tuple[InternalLink, ...]:
    """Create a bidirectional pillar/cluster link graph with contextual anchors."""
    pillar = _require_text("pillar slug", pillar_slug).strip("/")
    children = tuple(dict.fromkeys(slug.strip("/") for slug in article_slugs if slug.strip("/")))
    links: list[InternalLink] = []
    for child in children:
        anchor = child.replace("-", " ")
        links.append(InternalLink(pillar, child, anchor))
        links.append(InternalLink(child, pillar, f"all {pillar.replace('-', ' ')} services"))
    return tuple(links)


def plan_refreshes(performance: Iterable[SearchPerformance]) -> tuple[str, ...]:
    """Return keywords whose 30-day impression decline exceeds 15%."""
    return tuple(
        item.keyword
        for item in performance
        if should_refresh(item.previous_impressions, item.current_impressions)
    )


@dataclass(frozen=True)
class BusinessSEOContext:
    name: str
    url: str
    phone: str
    service_areas: tuple[str, ...]
    industry: str = "HVAC"
    price_range: Optional[str] = None


@dataclass(frozen=True)
class FAQ:
    question: str
    answer: str


@dataclass(frozen=True)
class SEOArticle:
    title: str
    description: str
    url: str
    date_published: date
    direct_answer: str
    subtitle: str
    sections: tuple[tuple[str, str], ...]
    faqs: tuple[FAQ, ...] = field(default_factory=tuple)


_PHONE_CLEAN_RE = re.compile(r"[^0-9+]")
_BUSINESS_SCHEMA_TYPES = {
    "HVAC": "HVACBusiness",
    "Plumber": "Plumber",
    "Electrician": "Electrician",
    "Pest Control": "LocalBusiness",
}


def _require_text(label: str, value: str) -> str:
    clean = value.strip()
    if not clean:
        raise SEOContentValidationError(f"{label} is required")
    return clean


def _require_http_url(label: str, value: str) -> str:
    clean = _require_text(label, value)
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SEOContentValidationError(f"{label} must be an absolute HTTP(S) URL")
    return clean


def _validate(business: BusinessSEOContext, article: SEOArticle) -> None:
    _require_text("business name", business.name)
    _require_http_url("business URL", business.url)
    _require_text("phone", business.phone)
    if not business.service_areas or not all(area.strip() for area in business.service_areas):
        raise SEOContentValidationError("at least one service area is required")
    _require_text("article title", article.title)
    _require_text("article description", article.description)
    _require_http_url("article URL", article.url)
    _require_text("direct answer", article.direct_answer)
    _require_text("subtitle", article.subtitle)
    if not article.sections:
        raise SEOContentValidationError("at least one article section is required")
    for heading, body in article.sections:
        _require_text("section heading", heading)
        _require_text("section body", body)
    for faq in article.faqs:
        _require_text("FAQ question", faq.question)
        _require_text("FAQ answer", faq.answer)


def build_schema_graph(business: BusinessSEOContext, article: SEOArticle) -> dict:
    """Build factual LocalBusiness, Article, and optional FAQ JSON-LD."""
    _validate(business, article)
    organization: dict = {
        "@type": _BUSINESS_SCHEMA_TYPES.get(business.industry, "LocalBusiness"),
        "@id": f"{business.url.rstrip('/')}/#organization",
        "name": business.name,
        "url": business.url,
        "telephone": business.phone,
        "areaServed": list(business.service_areas),
    }
    if business.price_range:
        organization["priceRange"] = business.price_range

    graph: list[dict] = [
        organization,
        {
            "@type": "Article",
            "headline": article.title,
            "description": article.description,
            "datePublished": article.date_published.isoformat(),
            "mainEntityOfPage": {"@type": "WebPage", "@id": article.url},
            "publisher": {"@id": organization["@id"]},
        },
    ]
    if article.faqs:
        graph.append(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": faq.question,
                        "acceptedAnswer": {"@type": "Answer", "text": faq.answer},
                    }
                    for faq in article.faqs
                ],
            }
        )
    return {"@context": "https://schema.org", "@graph": graph}


def render_seo_article_page(business: BusinessSEOContext, article: SEOArticle) -> str:
    """Render a semantic, mobile-first SEO article without raw HTML injection."""
    schema = build_schema_graph(business, article)
    esc = lambda value: html.escape(str(value), quote=True)
    phone_clean = _PHONE_CLEAN_RE.sub("", business.phone)
    sections = "\n".join(
        f"<section><h2>{esc(heading)}</h2><p>{esc(body)}</p></section>"
        for heading, body in article.sections
    )
    schema_json = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(article.title)}</title>
  <meta name="description" content="{esc(article.description)}">
  <link rel="canonical" href="{esc(article.url)}">
  <script type="application/ld+json">{schema_json}</script>
  <style>
    :root{{--ws-primary:#000080;--ws-action:#ff6600;--ws-blue:#4169e1;--ws-ink:#111827;--ws-surface:#f5f6f8}}
    *{{box-sizing:border-box}} body{{margin:0;color:var(--ws-ink);font-family:system-ui,-apple-system,sans-serif;line-height:1.65}}
    .status{{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;gap:1rem;padding:.7rem 1rem;background:var(--ws-primary);color:white;font-weight:750}}
    .status a{{color:white}} .hero,main{{width:min(800px,92vw);margin:auto}} .hero{{padding:3rem 0 2rem}}
    .answer{{padding:1rem 1.15rem;border-left:4px solid var(--ws-blue);border-radius:.4rem;background:#eef2ff}}
    h1{{color:var(--ws-primary);font-size:clamp(2rem,7vw,3.5rem);line-height:1.05;letter-spacing:-.035em}}
    h2{{color:var(--ws-primary);margin-top:2.5rem}} .cta{{display:flex;min-height:52px;align-items:center;justify-content:center;margin-top:1.5rem;padding:.8rem 1.3rem;border-radius:.75rem;background:var(--ws-action);color:white;font-weight:800;text-decoration:none}}
    main{{padding-bottom:4rem}} @media(min-width:700px){{.cta{{display:inline-flex;width:auto}}}}
  </style>
</head>
<body>
  <div class="status"><span>Serving {esc(business.service_areas[0])}</span><a href="tel:{esc(phone_clean)}">Call now</a></div>
  <header class="hero">
    <div class="answer"><strong>Quick answer:</strong> {esc(article.direct_answer)}</div>
    <h1>{esc(article.title)}</h1>
    <p>{esc(article.subtitle)}</p>
    <a class="cta" href="tel:{esc(phone_clean)}">Call {esc(business.phone)}</a>
  </header>
  <main>{sections}</main>
</body>
</html>
"""

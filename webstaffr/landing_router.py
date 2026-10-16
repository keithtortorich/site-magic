"""NetBuild.Pro public landing page and investor resources.

Serves the landing page at GET /, demo site previews, and the full
business plan PDF for investors.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

landing_router = APIRouter(tags=["public"])
logger = logging.getLogger("webstaffr.landing_router")
_INTAKE_PAGE = Path(__file__).parent / "templates" / "intake_start.html"
_NETBUILD_PAGE = Path(__file__).parent / "templates" / "netbuild_pro.html"

# Single source of truth for the public contact details. These appear in the
# investor JSON, the investor modal, and the lead-capture form, and previously
# drifted apart across all three.
#
# Confirmed by the founder 2026-07-28: mail goes to his Gmail, not to a mailbox
# on either webstaff.com or webstaffr.com. The stale keith@webstaff.com address
# that used to be here never resolved the domain-spelling conflict between
# LINK_MANIFEST.md ("webstaffr.com") and POST_DEPLOY_VERIFICATION.md
# ("webstaff.com"); that conflict still needs settling for the site URLs, but it
# no longer affects where mail lands. See TASKS.md Pending.
_CONTACT_EMAIL = "keithtortorich@gmail.com"
_CONTACT_PHONE = "(888) 302-8368"
_CONTACT_PHONE_TEL = "+18883028368"

# Small inline SVG icon set for the landing page -- same rationale as the
# customer-site renderer's icon set (webstaffr/templates/site/_icons.html):
# replaces plain-text bullets/numbering with real iconography, no external
# icon-library dependency, no build step. Defined as plain Python string
# constants here (rather than Jinja macros) because this page is a single
# inline-HTML string, not a Jinja template -- same visual language, native
# to this file's own architecture.
_ICON_CHECK = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<polyline points="20 6 9 17 4 12"/></svg>'
)
_ICON_X = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
)
_ICON_PHONE = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 '
    '19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 '
    '2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 '
    '2.81.7A2 2 0 0 1 22 16.92z"/></svg>'
)
_ICON_ARROW = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>'
)


@landing_router.get("/", response_class=None)
async def landing_page():
    """Serve the NetBuild.Pro public landing page (animated, Angel embedded)."""
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=_NETBUILD_PAGE.read_text())


@landing_router.get("/start", response_class=None)
async def intake_page():
    """Serve the one-page, tradesman-facing setup form."""
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=_INTAKE_PAGE.read_text())


def _render_landing_page() -> str:
    """Substitute contact details into the landing page template.

    Plain token replacement rather than an f-string: the template is mostly
    CSS and JavaScript, so every brace in it would have to be doubled to make
    f-string interpolation safe. Tokens keep the markup readable and keep the
    contact details defined in exactly one place.
    """
    return (
        _LANDING_PAGE_HTML
        .replace("__CONTACT_EMAIL__", _CONTACT_EMAIL)
        .replace("__CONTACT_PHONE_TEL__", _CONTACT_PHONE_TEL)
        .replace("__CONTACT_PHONE__", _CONTACT_PHONE)
        .replace("__ICON_CHECK__", _ICON_CHECK)
        .replace("__ICON_X__", _ICON_X)
        .replace("__ICON_PHONE__", _ICON_PHONE)
        .replace("__ICON_ARROW__", _ICON_ARROW)
    )


@landing_router.get("/investors/pitch")
@landing_router.get("/investors/pitch.pdf")
async def investor_pitch():
    """Serve the full business plan PDF (when available)."""
    from fastapi.responses import FileResponse, JSONResponse
    import os

    pdf_path = os.path.join(os.path.dirname(__file__), "investor_pitch.pdf")
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename="NetBuildPro_Pitch.pdf")

    # Fallback: return investor summary from INVESTOR_EMAIL_FINAL.md
    return JSONResponse({
        "message": "NetBuild.Pro Investment Overview",
        "narrative": "You don't need more leads. You need to stop losing the ones you already have.",
        "problem": "Home-service contractors need a reliable way to capture incoming demand while they are working.",
        "solution": "NetBuild.Pro builds the customer site first, then activates call handling, CRM routing, and booking after each approved integration is verified.",
        "pricing": {"office_staff_monthly": 497},
        "ask": "$15K-50K SAFE",
        "contact": {
            "email": _CONTACT_EMAIL,
            "phone": _CONTACT_PHONE
        },
        "pdf": "Full PDF available at deployment. Email for early access."
    })


# /demos/{slug} and /demo-sites/{file_name} now live in demo_router.py,
# generated by the real Site Magic pipeline (ADR-030) instead of this
# module's old static-file serve / provisioned-tenant lookup. Retired
# here, not deleted from history -- see
# docs/ADR-030_DEMO_SITES_VIA_SITEMAGIC.md for the replacement design.

# Landing page: Matches agency site aesthetics (teal + gold + copper, clean pro layout)
# Copy from WEBSTAFFR_AGENCY_SITE_COPY_HORMOZI_VOSS.md
# Design: Teal primary, gold accents, copper CTAs, cream backgrounds (ADR-022 palette)
# Structure: Utility bar → hero → what's included → pricing → FAQ → CTA footer
# Colors: Teal (#1a4d5e), gold (#d4a574), copper (#c85a3a), cream (#f5f1e8), dark slate (#2a3a42)
_LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="NetBuild.Pro gives contractors a trained virtual office team that answers calls, follows up with leads, and keeps the schedule full.">
    <title>NetBuild.Pro | Never Let a Paid Lead Go Unanswered</title>
    <style>
    :root {
        --ws-primary-teal: #1a4d5e;
        --ws-gold: #d4a574;
        --ws-copper: #c85a3a;
        --ws-cream: #f5f1e8;
        --ws-dark-slate: #2a3a42;
        --ws-light-gray: #f0f0f0;
        --ws-border: #e2e6ec;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #333; background: #fff; }

    .ws-utility-bar { background: var(--ws-primary-teal); color: white; padding: 8px 0; font-size: 0.875rem; }
    .ws-utility-bar-inner { max-width: 1200px; margin: 0 auto; padding: 0 20px; display: flex; justify-content: flex-end; gap: 40px; align-items: center; }
    .ws-utility-phone { display: flex; gap: 8px; align-items: center; }
    .ws-utility-item-accent { font-weight: 700; color: var(--ws-gold); }

    .ws-header { background: white; border-bottom: 1px solid var(--ws-border); position: sticky; top: 0; z-index: 100; }
    .ws-header-inner { max-width: 1200px; margin: 0 auto; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }
    .ws-brand { display: flex; gap: 12px; align-items: center; font-weight: 700; font-size: 1.25rem; color: var(--ws-primary-teal); }
    .ws-logo { width: 32px; height: 32px; }
    .ws-nav { display: flex; gap: 32px; }
    .ws-nav-link { color: #666; text-decoration: none; font-size: 0.95rem; transition: color 0.2s; }
    .ws-nav-link:hover { color: var(--ws-copper); }
    .ws-nav-cta { background: var(--ws-copper); color: white; padding: 10px 20px; border-radius: 4px; text-decoration: none; font-size: 0.95rem; font-weight: 600; transition: background 0.2s; }
    .ws-nav-cta:hover { background: #b04a2a; }

    .ws-hero { background: linear-gradient(135deg, var(--ws-primary-teal) 0%, #0f3a47 100%); color: white; padding: 80px 20px; text-align: center; }
    .ws-hero-inner { max-width: 700px; margin: 0 auto; }
    .ws-hero-title { font-size: 2.8rem; font-weight: 700; margin-bottom: 16px; line-height: 1.2; }
    .ws-hero-subtitle { font-size: 1.2rem; color: rgba(255,255,255,0.9); margin-bottom: 32px; line-height: 1.5; }
    .ws-hero-cta { display: inline-block; background: var(--ws-copper); color: white; padding: 14px 32px; border-radius: 4px; text-decoration: none; font-weight: 600; transition: background 0.2s; font-size: 1rem; }
    .ws-hero-cta:hover { background: #b04a2a; }

    .ws-section { padding: 60px 20px; }
    .ws-section-inner { max-width: 1200px; margin: 0 auto; }
    .ws-section-heading { font-size: 2rem; font-weight: 700; color: var(--ws-primary-teal); margin-bottom: 16px; }
    .ws-section-subheading { font-size: 1.1rem; color: #666; margin-bottom: 40px; }

    .ws-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 32px; margin-bottom: 40px; }
    .ws-feature { background: var(--ws-cream); padding: 32px; border-radius: 4px; border-left: 4px solid var(--ws-gold); }
    .ws-feature-title { font-size: 1.2rem; font-weight: 700; color: var(--ws-primary-teal); margin-bottom: 12px; }
    .ws-feature-text { color: #666; font-size: 0.95rem; line-height: 1.6; }

    .ws-pricing { background: var(--ws-cream); padding: 60px 20px; }
    .ws-pricing-inner { max-width: 1200px; margin: 0 auto; }
    .ws-pricing-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; margin-top: 40px; }
    .ws-pricing-card { background: white; border: 1px solid var(--ws-border); padding: 40px 24px; border-radius: 4px; text-align: center; transition: transform 0.2s, box-shadow 0.2s; }
    .ws-pricing-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
    .ws-pricing-card.featured { border: 2px solid var(--ws-copper); background: white; }
    .ws-pricing-label { font-size: 0.85rem; font-weight: 600; color: var(--ws-copper); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
    .ws-pricing-name { font-size: 1.5rem; font-weight: 700; color: var(--ws-primary-teal); margin-bottom: 16px; }
    .ws-pricing-amount { font-size: 2.5rem; font-weight: 700; color: var(--ws-copper); margin-bottom: 4px; }
    .ws-pricing-period { font-size: 0.9rem; color: #999; margin-bottom: 24px; }
    .ws-pricing-desc { font-size: 0.95rem; color: #666; margin-bottom: 24px; }
    .ws-pricing-cta { display: block; background: var(--ws-copper); color: white; padding: 12px 24px; border-radius: 4px; text-decoration: none; font-weight: 600; transition: background 0.2s; }
    .ws-pricing-cta:hover { background: #b04a2a; }

    .ws-faq { padding: 60px 20px; }
    .ws-faq-inner { max-width: 800px; margin: 0 auto; }
    .ws-faq-item { margin-bottom: 32px; }
    .ws-faq-q { font-size: 1.1rem; font-weight: 700; color: var(--ws-primary-teal); margin-bottom: 8px; }
    .ws-faq-a { color: #666; font-size: 0.95rem; line-height: 1.6; }

    .ws-demo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin-top: 40px; }
    .ws-demo-btn { display: flex; flex-direction: column; align-items: center; justify-content: center; background: white; border: 2px solid var(--ws-border); padding: 36px 24px; border-radius: 4px; text-decoration: none; transition: all 0.2s; min-height: 160px; }
    .ws-demo-btn:hover { border-color: var(--ws-copper); background: var(--ws-cream); transform: translateY(-4px); }
    .ws-demo-name { font-size: 1.1rem; font-weight: 700; color: var(--ws-primary-teal); margin-bottom: 8px; text-align: center; }
    .ws-demo-desc { font-size: 0.85rem; color: #999; text-align: center; }

    .ws-footer { background: var(--ws-dark-slate); color: white; padding: 60px 20px 24px; }
    .ws-footer-inner { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 40px; margin-bottom: 40px; }
    .ws-footer-heading { font-size: 1.125rem; font-weight: 700; margin-bottom: 12px; }
    .ws-footer-text { font-size: 0.9rem; line-height: 1.6; color: rgba(255,255,255,0.8); }
    .ws-footer-links { list-style: none; }
    .ws-footer-links li { margin-bottom: 6px; }
    .ws-footer-links a { color: rgba(255,255,255,0.8); text-decoration: none; font-size: 0.9rem; transition: color 0.2s; }
    .ws-footer-links a:hover { color: var(--ws-gold); }
    .ws-footer-bottom { border-top: 1px solid rgba(255,255,255,0.1); padding-top: 20px; text-align: center; }
    .ws-footer-copyright { font-size: 0.8rem; color: rgba(255,255,255,0.6); }

    /* Motion: smooth scroll reveals */
    .ws-reveal { opacity: 0; transform: translateY(20px); transition: opacity 0.6s ease, transform 0.6s ease; }
    .ws-reveal.visible { opacity: 1; transform: translateY(0); }

    @media (max-width: 768px) {
        .ws-nav { display: none; }
        .ws-hero-title { font-size: 2rem; }
        .ws-section-heading { font-size: 1.5rem; }
        .ws-utility-bar-inner { flex-direction: column; gap: 12px; justify-content: center; }
    }
    </style>
</head>
<body>
    <div class="ws-utility-bar">
        <div class="ws-utility-bar-inner">
            <div class="ws-utility-phone">(888) 302-8368</div>
            <div><span class="ws-utility-item-accent">Built for</span> Home Services</div>
        </div>
    </div>

    <header class="ws-header">
        <div class="ws-header-inner">
            <div class="ws-brand">
                <svg width="24" height="24" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" class="ws-logo">
                    <rect x="10" y="10" width="30" height="30" fill="#1a4d5e" rx="4"/>
                    <rect x="50" y="10" width="30" height="30" fill="#d4a574" rx="4"/>
                    <rect x="10" y="50" width="30" height="30" fill="#d4a574" rx="4"/>
                    <rect x="50" y="50" width="30" height="30" fill="#1a4d5e" rx="4"/>
                </svg>
                <span>NetBuild.Pro</span>
            </div>
            <nav class="ws-nav">
                <a href="/" class="ws-nav-link">Home</a>
                <a href="#how" class="ws-nav-link">How It Works</a>
                <a href="#pricing" class="ws-nav-link">Pricing</a>
                <a href="#faq" class="ws-nav-link">FAQ</a>
            </nav>
            <a href="/start" class="ws-nav-cta">Get Started</a>
        </div>
    </header>

    <div class="ws-hero">
        <div class="ws-hero-inner">
            <h1 class="ws-hero-title">Never Let a Paid Lead Go Unanswered</h1>
            <p class="ws-hero-subtitle">NetBuild.Pro builds your customer site and activates a trained AI receptionist to answer calls, follow up with leads, and keep your schedule full.</p>
            <a href="/start" class="ws-hero-cta">Start Your Site</a>
        </div>
    </div>

    <section class="ws-section" id="how">
        <div class="ws-section-inner">
            <h2 class="ws-section-heading">What NetBuild.Pro Does</h2>
            <p class="ws-section-subheading">A complete receptionist workflow, verified step by step.</p>
            <div class="ws-features ws-reveal">
                <div class="ws-feature">
                    <div class="ws-feature-title">1. Build Your Site</div>
                    <div class="ws-feature-text">We generate a customer-ready website from the business information you provide: services, service area, contact details, and Angel chat integration.</div>
                </div>
                <div class="ws-feature">
                    <div class="ws-feature-title">2. Activate Call Handling</div>
                    <div class="ws-feature-text">After your phone, Retell, calendar, and CRM integrations pass verification, Angel answers incoming calls, qualifies leads, and routes them to you.</div>
                </div>
                <div class="ws-feature">
                    <div class="ws-feature-title">3. Enable Booking</div>
                    <div class="ws-feature-text">Customers book appointments directly into your calendar. Angel follows up on no-shows and reschedules as needed. Nothing is automated until it passes testing.</div>
                </div>
            </div>
        </div>
    </section>

    <section class="ws-pricing" id="pricing">
        <div class="ws-pricing-inner">
            <h2 class="ws-section-heading">Simple Pricing</h2>
            <p class="ws-section-subheading">One service level designed for home-service contractors at launch.</p>
            <div class="ws-pricing-cards">
                <div class="ws-pricing-card featured ws-reveal">
                    <div class="ws-pricing-label">Most Popular</div>
                    <div class="ws-pricing-name">Office Staff</div>
                    <div class="ws-pricing-amount">$497</div>
                    <div class="ws-pricing-period">/month</div>
                    <div class="ws-pricing-desc">Website generation, call handling, lead routing, and booking workflow.</div>
                    <a href="/start" class="ws-pricing-cta">Start Setup</a>
                </div>
            </div>
            <p style="margin-top: 32px; text-align: center; color: #666; font-size: 0.95rem;">Other service levels and custom pricing available after launch. <a href="tel:__CONTACT_PHONE_TEL__" style="color: var(--ws-copper); text-decoration: none;">Call us</a> for details.</p>
        </div>
    </section>

    <section class="ws-section" id="demos">
        <div class="ws-section-inner">
            <h2 class="ws-section-heading">See It In Action</h2>
            <p class="ws-section-subheading">Explore demo sites built for different trades. Each shows your finished website with Angel chat and booking integrated.</p>
            <div class="ws-demo-grid ws-reveal">
                <a href="/demos/hvac" class="ws-demo-btn">
                    <div class="ws-demo-name">HVAC</div>
                    <div class="ws-demo-desc">Heating & Cooling</div>
                </a>
                <a href="/demos/plumbing" class="ws-demo-btn">
                    <div class="ws-demo-name">Plumbing</div>
                    <div class="ws-demo-desc">Water & Drain</div>
                </a>
                <a href="/demos/electrical" class="ws-demo-btn">
                    <div class="ws-demo-name">Electrical</div>
                    <div class="ws-demo-desc">Wiring & Panels</div>
                </a>
                <a href="/demos/roofing" class="ws-demo-btn">
                    <div class="ws-demo-name">Roofing</div>
                    <div class="ws-demo-desc">Repairs & Installation</div>
                </a>
                <a href="/demos/landscaping" class="ws-demo-btn">
                    <div class="ws-demo-name">Landscaping</div>
                    <div class="ws-demo-desc">Design & Maintenance</div>
                </a>
                <a href="/demos/pest-control" class="ws-demo-btn">
                    <div class="ws-demo-name">Pest Control</div>
                    <div class="ws-demo-desc">Treatment & Prevention</div>
                </a>
                <a href="/demos/garage-door" class="ws-demo-btn">
                    <div class="ws-demo-name">Garage Doors</div>
                    <div class="ws-demo-desc">Install & Repair</div>
                </a>
                <a href="/demos/tree-service" class="ws-demo-btn">
                    <div class="ws-demo-name">Tree Service</div>
                    <div class="ws-demo-desc">Trimming & Removal</div>
                </a>
                <a href="/demos/water-restoration" class="ws-demo-btn">
                    <div class="ws-demo-name">Water Restoration</div>
                    <div class="ws-demo-desc">Damage & Cleanup</div>
                </a>
                <a href="/demos/cleaning" class="ws-demo-btn">
                    <div class="ws-demo-name">Cleaning Services</div>
                    <div class="ws-demo-desc">Residential Cleaning</div>
                </a>
            </div>
            <p style="margin-top:20px;text-align:center;"><a href="/demos" style="color:var(--ws-copper);text-decoration:none;">See all demo sites &rarr;</a></p>
        </div>
    </section>

    <section class="ws-faq" id="faq">
        <div class="ws-faq-inner">
            <h2 class="ws-section-heading">Common Questions</h2>
            <div class="ws-faq-item ws-reveal">
                <div class="ws-faq-q">When does call handling become active?</div>
                <div class="ws-faq-a">After you've provided your phone number, connected Retell, configured your calendar, and approved GHL settings. Each integration passes an end-to-end verification before we show it as live.</div>
            </div>
            <div class="ws-faq-item ws-reveal">
                <div class="ws-faq-q">Can the site launch before voice automation?</div>
                <div class="ws-faq-a">Yes. Site generation and call handling are verified separately. Your site goes live as soon as it's built and reviewed. Call handling activates when its integrations are ready.</div>
            </div>
            <div class="ws-faq-item ws-reveal">
                <div class="ws-faq-q">Does Angel use my sales process?</div>
                <div class="ws-faq-a">Yes. We import your intake questions, pricing, objection responses, and escalation rules. Angel sounds like your team because it is trained on your process.</div>
            </div>
            <div class="ws-faq-item ws-reveal">
                <div class="ws-faq-q">What if an integration fails?</div>
                <div class="ws-faq-a">It stays disabled while your site and other verified parts continue to operate. We don't risk your customer data with untested automation.</div>
            </div>
            <div class="ws-faq-item ws-reveal">
                <div class="ws-faq-q">Who controls my business information?</div>
                <div class="ws-faq-a">You do. You provide the services, service area, pricing, and business rules. NetBuild.Pro never invents information on your behalf.</div>
            </div>
            <div class="ws-faq-item ws-reveal">
                <div class="ws-faq-q">What happens next?</div>
                <div class="ws-faq-a">Complete the setup form with your business details. We'll generate your site and send you a checklist of the remaining integration steps.</div>
            </div>
        </div>
    </section>

    <footer class="ws-footer">
        <div class="ws-footer-inner">
            <div>
                <h3 class="ws-footer-heading">NetBuild.Pro</h3>
                <p class="ws-footer-text">Customer websites and call handling for home service contractors.</p>
            </div>
            <div>
                <h4 class="ws-footer-heading">Product</h4>
                <ul class="ws-footer-links">
                    <li><a href="#how">How It Works</a></li>
                    <li><a href="#pricing">Pricing</a></li>
                    <li><a href="/start">Get Started</a></li>
                </ul>
            </div>
            <div>
                <h4 class="ws-footer-heading">Company</h4>
                <ul class="ws-footer-links">
                    <li><a href="/agency">For Agencies</a></li>
                    <li><a href="/agency/contact">Contact</a></li>
                </ul>
            </div>
            <div>
                <h4 class="ws-footer-heading">Contact</h4>
                <p class="ws-footer-text">
                    <a href="mailto:__CONTACT_EMAIL__" style="color: var(--ws-gold); text-decoration: none;">__CONTACT_EMAIL__</a><br>
                    <a href="tel:__CONTACT_PHONE_TEL__" style="color: var(--ws-gold); text-decoration: none;">__CONTACT_PHONE__</a>
                </p>
            </div>
        </div>
        <div class="ws-footer-bottom">
            <p class="ws-footer-copyright">&copy; 2026 NetBuild.Pro. All rights reserved.</p>
        </div>
    </footer>

    <script>
    // Scroll reveal for .ws-reveal sections
    (function () {
        var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (prefersReduced) {
            document.querySelectorAll('.ws-reveal').forEach(el => el.classList.add('visible'));
            return;
        }
        if (!('IntersectionObserver' in window)) {
            document.querySelectorAll('.ws-reveal').forEach(el => el.classList.add('visible'));
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });
        document.querySelectorAll('.ws-reveal').forEach(el => io.observe(el));
    })();
    </script>
</body>
</html>
"""

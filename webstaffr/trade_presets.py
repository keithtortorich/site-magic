"""Per-trade presentation hints for the intake form.

Presentation-layer only -- none of this affects the intake_submissions
schema (webstaffr/migrations/0003_intake_submissions.sql), which is the
same for every industry. What varies per trade is: example/placeholder
text shown while filling out the form, and which field-service-management
software options are offered.

Ported from the legacy webstaff repo's intake/intake.html (TRADE_HINTS,
INDUSTRY_SOFTWARE) and builder/site_generator.py (INDUSTRY_PRESETS'
default_services) -- see the CLAUDE.md session addendum for provenance.
Values are illustrative placeholder copy, not real business data.

SUPPORTED_INDUSTRIES narrowed to WebStaffr's priority trade list
(founder direction, 2026-07-27): the trades where speed-to-lead most
directly determines whether a call turns into revenue -- emergency
demand, high-LTV jobs, or both. Contractor/Restaurant/Med Spa/Dentist/
Salon (the prior list) are dropped from the curated set; "Other" stays
as the always-available fallback so intake never hard-fails for a
business type outside this list.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class TradeHint(TypedDict):
    biz: str
    tagline: str
    differentiator: str
    services: list[str]
    license: str
    keywords: str
    certifications: str


class TradeSoftware(TypedDict):
    label: str
    options: list[str]
    booking_placeholder: str


SUPPORTED_INDUSTRIES: list[str] = [
    "HVAC",
    "Plumber",
    "Electrician",
    "Roofing",
    "Water Damage Restoration",
    "Garage Door Repair",
    "Pest Control",
    "Landscaping",
    "Tree Service",
    "Cleaning Services",
    "Other",
]

# Industries that don't map 1:1 to a canonical key above (mirrors
# INDUSTRY_NORMALIZE in the legacy site_generator.py).
INDUSTRY_ALIASES: dict[str, str] = {
    "Plumbing": "Plumber",
    "Electrical": "Electrician",
    "Restoration": "Water Damage Restoration",
    "Water Damage": "Water Damage Restoration",
    "Garage Door": "Garage Door Repair",
    "Exterminator": "Pest Control",
    "Lawn Care": "Landscaping",
    "Lawn Maintenance": "Landscaping",
    "Tree Trimming": "Tree Service",
    "Tree Removal": "Tree Service",
    "House Cleaning": "Cleaning Services",
    "Maid Service": "Cleaning Services",
}

TRADE_HINTS: dict[str, TradeHint] = {
    "HVAC": {
        "biz": "Desert Air HVAC",
        "tagline": "Phoenix's fastest HVAC - same-day service, always.",
        "differentiator": "We're the only HVAC company in Phoenix that guarantees same-day service in writing. No call center, no runaround.",
        "services": ["AC Repair", "AC Installation", "Furnace Repair", "Air Quality / Duct Cleaning", "Emergency HVAC"],
        "license": "ROC 123456 - NATE Certified",
        "keywords": "hvac repair phoenix, ac not cooling, emergency ac repair scottsdale, furnace replacement phoenix, air conditioning tune-up",
        "certifications": "BBB A+, NATE Certified, ACCA Member, EPA 608",
    },
    "Plumber": {
        "biz": "Desert Flow Plumbing",
        "tagline": "Phoenix plumbers on call 24/7 - we fix it right the first time.",
        "differentiator": "Upfront flat-rate pricing before we start any work. No surprise invoices, ever.",
        "services": ["Leak Detection & Repair", "Water Heater Replacement", "Drain Cleaning", "Sewer Line Inspection", "Emergency Plumbing"],
        "license": "ROC 234567",
        "keywords": "plumber phoenix, emergency plumber, water heater replacement scottsdale, drain cleaning phoenix, leak repair",
        "certifications": "Licensed & Bonded, BBB A+, HomeAdvisor Top Rated",
    },
    "Electrician": {
        "biz": "Bright Force Electric",
        "tagline": "Licensed electricians in Phoenix - panel upgrades, rewires, same-day.",
        "differentiator": "Every job is inspected and code-certified before we leave. No shortcuts.",
        "services": ["Panel Upgrades & Replacements", "EV Charger Installation", "Outlet & Switch Repair", "Whole-Home Rewire", "Emergency Electrical"],
        "license": "ROC 345678 - State License CR-11",
        "keywords": "electrician phoenix, panel upgrade scottsdale, ev charger installation, electrical repair phoenix, licensed electrician",
        "certifications": "Licensed & Bonded, BBB A+, NABCEP Certified",
    },
    "Roofing": {
        "biz": "Peak Roofing Solutions",
        "tagline": "Phoenix roofers trusted by 1,200+ homeowners - free inspection, lifetime workmanship.",
        "differentiator": "We're one of the only roofers in the Valley that documents every inspection with photos and a written report - before we quote anything.",
        "services": ["Roof Replacement", "Roof Repair", "Storm Damage Inspection", "Flat Roof Systems", "New Construction Roofing"],
        "license": "ROC 456789 - Licensed & Bonded",
        "keywords": "roofing contractor phoenix, roof replacement scottsdale, storm damage roof repair, flat roof phoenix, free roof inspection",
        "certifications": "Owens Corning Preferred, GAF Master Elite, BBB A+",
    },
    "Water Damage Restoration": {
        "biz": "Rapid Dry Restoration",
        "tagline": "Phoenix water damage restoration - on-site in 60 minutes, day or night.",
        "differentiator": "IICRC-certified technicians on-site within 60 minutes, 24/7 - no answering service, no waiting.",
        "services": ["Water Extraction", "Structural Drying", "Mold Remediation", "Smoke & Fire Damage Restoration", "Emergency Board-Up"],
        "license": "AZ ROC 678901 - IICRC Certified Firm",
        "keywords": "water damage restoration phoenix, flood cleanup scottsdale, emergency water extraction, mold remediation phoenix, fire damage restoration",
        "certifications": "IICRC Certified, BBB A+, Licensed & Insured",
    },
    "Garage Door Repair": {
        "biz": "Valley Garage Door Pros",
        "tagline": "Phoenix garage door repair - same-day service, upfront pricing.",
        "differentiator": "We carry parts for every major brand on the truck, so most repairs finish in one visit.",
        "services": ["Spring Repair & Replacement", "Opener Installation & Repair", "Panel & Track Repair", "New Garage Door Installation", "Emergency Garage Door Repair"],
        "license": "ROC 789012 - Licensed & Bonded",
        "keywords": "garage door repair phoenix, garage door spring replacement scottsdale, garage door opener repair, same day garage door service, emergency garage door repair",
        "certifications": "IDA Member, BBB A+, Licensed & Bonded",
    },
    "Pest Control": {
        "biz": "Sonoran Pest Solutions",
        "tagline": "Phoenix pest control - scorpions, termites, and everything in between.",
        "differentiator": "Every treatment plan is backed by a written re-service guarantee - if pests come back between visits, so do we, free.",
        "services": ["General Pest Control", "Scorpion Control", "Termite Treatment", "Rodent Exclusion", "Quarterly Maintenance Plans"],
        "license": "AZ Pest Control License #34567",
        "keywords": "pest control phoenix, scorpion control scottsdale, termite treatment phoenix, exterminator near me, rodent control phoenix",
        "certifications": "AZ Structural Pest Control Licensed, BBB A+, QualityPro Certified",
    },
    "Landscaping": {
        "biz": "Desert Bloom Landscaping",
        "tagline": "Phoenix landscaping - xeriscape design, installation, and maintenance.",
        "differentiator": "Every design is built for the Sonoran Desert climate first - low water use without sacrificing curb appeal.",
        "services": ["Landscape Design & Installation", "Xeriscape & Drought-Tolerant Design", "Irrigation Repair", "Tree & Shrub Trimming", "Seasonal Maintenance Plans"],
        "license": "AZ ROC 890123 - Landscape Contractor",
        "keywords": "landscaping phoenix, xeriscape design scottsdale, irrigation repair phoenix, desert landscaping, landscape maintenance near me",
        "certifications": "Licensed ROC, BBB A+, Certified Landscape Professional",
    },
    "Tree Service": {
        "biz": "Canopy Tree Care",
        "tagline": "Phoenix tree service - trimming, removal, and storm cleanup.",
        "differentiator": "Every crew is ISA Certified Arborist-led, so pruning decisions come from training, not guesswork.",
        "services": ["Tree Trimming & Pruning", "Tree Removal", "Stump Grinding", "Storm Damage Cleanup", "Palm Tree Care"],
        "license": "AZ ROC 901234 - Licensed & Insured",
        "keywords": "tree service phoenix, tree removal scottsdale, tree trimming near me, stump grinding phoenix, storm damage tree cleanup",
        "certifications": "ISA Certified Arborist, BBB A+, TCIA Member",
    },
    "Cleaning Services": {
        "biz": "Sparkle Valley Cleaning",
        "tagline": "Phoenix cleaning services - reliable, bonded, and background-checked.",
        "differentiator": "The same two-person team cleans your home every visit - no rotating strangers, ever.",
        "services": ["Recurring House Cleaning", "Deep Cleaning", "Move-In/Move-Out Cleaning", "Post-Construction Cleaning", "Office & Commercial Cleaning"],
        "license": "AZ Business License - Bonded & Insured",
        "keywords": "house cleaning phoenix, cleaning service scottsdale, deep cleaning near me, move out cleaning phoenix, office cleaning phoenix",
        "certifications": "Bonded & Insured, BBB A+, Background-Checked Staff",
    },
    "Other": {
        "biz": "Your Business Name",
        "tagline": "Your city's most trusted [service] - [your differentiator here].",
        "differentiator": "Describe the #1 reason a customer should choose you over anyone else in your market.",
        "services": ["Your Top Service", "Your Second Service", "Your Third Service"],
        "license": "License # / Bond # / Certification",
        "keywords": "your service your city, [service] near me, best [service] [city]",
        "certifications": "Your Key Certifications, Awards, Affiliations",
    },
}

TRADE_SOFTWARE: dict[str, TradeSoftware] = {
    "HVAC": {"label": "Do you use a field service management system?", "options": ["ServiceTitan", "Jobber", "Housecall Pro", "ServiceFusion", "Other", "None"], "booking_placeholder": "e.g. ServiceTitan, Calendly, or none"},
    "Plumber": {"label": "Do you use a field service management system?", "options": ["ServiceTitan", "Jobber", "Housecall Pro", "ServiceFusion", "Other", "None"], "booking_placeholder": "e.g. Jobber, ServiceTitan, or none"},
    "Electrician": {"label": "Do you use a field service management system?", "options": ["ServiceTitan", "Jobber", "Housecall Pro", "ServiceFusion", "Other", "None"], "booking_placeholder": "e.g. Jobber, ServiceTitan, or none"},
    "Roofing": {"label": "Do you use a field service management system?", "options": ["JobNimbus", "AccuLynx", "Jobber", "Roofr", "Other", "None"], "booking_placeholder": "e.g. JobNimbus, AccuLynx, or none"},
    "Water Damage Restoration": {"label": "Do you use a restoration job management system?", "options": ["Xactimate", "DASH", "Encircle", "Jobber", "Other", "None"], "booking_placeholder": "e.g. Xactimate, DASH, or none"},
    "Garage Door Repair": {"label": "Do you use a field service management system?", "options": ["ServiceTitan", "Jobber", "Housecall Pro", "ServiceFusion", "Other", "None"], "booking_placeholder": "e.g. Jobber, ServiceTitan, or none"},
    "Pest Control": {"label": "Do you use a pest control routing/service system?", "options": ["PestPac", "FieldRoutes", "Briostack", "ServSuite", "Other", "None"], "booking_placeholder": "e.g. PestPac, FieldRoutes, or none"},
    "Landscaping": {"label": "Do you use a landscape business management system?", "options": ["Aspire", "Jobber", "LMN", "Service Autopilot", "Other", "None"], "booking_placeholder": "e.g. Aspire, Jobber, or none"},
    "Tree Service": {"label": "Do you use a tree service business management system?", "options": ["Aspire", "Arborgold", "Jobber", "SingleOps", "Other", "None"], "booking_placeholder": "e.g. Arborgold, SingleOps, or none"},
    "Cleaning Services": {"label": "Do you use a cleaning business management system?", "options": ["Jobber", "Housecall Pro", "ZenMaid", "Launch27", "Other", "None"], "booking_placeholder": "e.g. ZenMaid, Housecall Pro, or none"},
    "Other": {"label": "Do you use any scheduling or management software?", "options": ["Other", "None"], "booking_placeholder": "e.g. Calendly, or none"},
}


def normalize_industry(industry: str) -> str:
    """Map a free-text/alias industry value to its canonical preset key.
    Unknown industries fall back to 'Other' rather than raising -- intake
    should never hard-fail just because a business picked a trade we don't
    have bespoke copy for yet."""
    canonical = INDUSTRY_ALIASES.get(industry, industry)
    return canonical if canonical in TRADE_HINTS else "Other"


def get_preset(industry: str) -> dict:
    """Returns the combined hint + software preset for an industry, always
    resolvable (falls back to 'Other'). Used by GET /intake/presets/{industry}
    so the frontend can adapt placeholder copy and FSM options per trade
    without this backend owning any UI itself."""
    key = normalize_industry(industry)
    return {
        "industry": key,
        "hints": TRADE_HINTS[key],
        "software": TRADE_SOFTWARE.get(key, TRADE_SOFTWARE["Other"]),
    }

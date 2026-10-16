"""NetBuild.Pro agency site, separate from generated customer sites.

Served at GET /agency/* using Jinja2 templates with the new brand palette
(teal + gold + copper). Copy from WEBSTAFFR_AGENCY_SITE_COPY_HORMOZI_VOSS.md.
Design from WEBSTAFFR_AGENCY_SITE_DESIGN_DIRECTION.md.

Templates live on disk at webstaffr/templates/agency/ (this is the single
source of truth -- there used to be a second, drifting copy hardcoded in
this file as a DictLoader dict; that's gone). Reading them fresh per
request is the same posture site_render_router.py takes for its own
templates and static assets: no filesystem write, small files, and
Vercel's serverless model doesn't charge meaningfully for a read.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

agency_router = APIRouter(tags=["agency"])

_TEMPLATES_DIR = Path(__file__).parent / "templates" / "agency"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


@agency_router.get("/agency", response_class=HTMLResponse)
@agency_router.get("/agency/", response_class=HTMLResponse)
async def agency_home():
    template = _jinja_env.get_template("home.html")
    return HTMLResponse(content=template.render())


@agency_router.get("/agency/how-it-works", response_class=HTMLResponse)
async def agency_how_it_works():
    template = _jinja_env.get_template("how_it_works.html")
    return HTMLResponse(content=template.render())


@agency_router.get("/agency/pricing", response_class=HTMLResponse)
async def agency_pricing():
    template = _jinja_env.get_template("pricing.html")
    return HTMLResponse(content=template.render())


@agency_router.get("/agency/faq", response_class=HTMLResponse)
async def agency_faq():
    template = _jinja_env.get_template("faq.html")
    return HTMLResponse(content=template.render())


@agency_router.get("/agency/about", response_class=HTMLResponse)
async def agency_about():
    template = _jinja_env.get_template("about.html")
    return HTMLResponse(content=template.render())


@agency_router.get("/agency/contact", response_class=HTMLResponse)
async def agency_contact():
    template = _jinja_env.get_template("contact.html")
    return HTMLResponse(content=template.render())

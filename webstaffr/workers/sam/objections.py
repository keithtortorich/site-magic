"""Objection handling: professional, educational responses to common sales objections.

Educational tone, not pushy. Includes caveats and encourages site visits.
No promises; references that specifics will be discussed with the team.
"""

from __future__ import annotations

from typing import Optional


class ObjectionLibrary:
    """Per-trade objection responses."""

    # Common objections and professional responses, by industry and objection type.
    # Response templates use {business_name} and {services} as placeholders for personalization.
    _OBJECTIONS: dict[str, dict[str, str]] = {
        # Default responses for any industry
        "default": {
            "cost": (
                "I understand cost is important. Here's what we've found: many customers underestimate how much "
                "a bad or incomplete job costs down the road—rework, damage to surrounding systems, or the need for "
                "an emergency call. Our upfront pricing reflects the quality and warranty our team stands behind. "
                "We're happy to walk through options during the site visit."
            ),
            "timeline": (
                "Timing depends on the work needed and our schedule. During the site visit, we'll give you exact "
                "dates and let you know what we can prioritize. Many jobs are faster than you'd expect once we get "
                "on-site and see the full scope."
            ),
            "warranty": (
                "Our work is backed by our workmanship guarantee. The team will explain exactly what's covered "
                "and for how long—every job is different, so we detail this during the inspection."
            ),
            "availability": (
                "We're committed to fitting you in. Let's find a time that works during the site visit consultation, "
                "and if we can't, we'll refer you to a trusted partner."
            ),
            "trust": (
                "We get it—there are a lot of fly-by-night operators. Check out our reviews, licenses, and references. "
                "We're not afraid of scrutiny, and we back every job with our name and guarantee."
            ),
        },
        # HVAC-specific responses
        "HVAC": {
            "cost": (
                "AC and heating are expensive because they're critical. A cheap repair often fails weeks later, "
                "leaving you without comfort in the middle of summer or winter. We quote fairly based on the actual "
                "work needed. Our team will show you exactly what's wrong and why during the visit."
            ),
            "timeline": (
                "Most HVAC repairs finish same-day. Replacements usually take 1–2 days. We'll give you a solid timeline "
                "once we inspect the system."
            ),
            "warranty": (
                "Parts come with manufacturer warranties. Our labor is guaranteed for 1 year, and we stand behind all work. "
                "The team will detail this when they arrive."
            ),
        },
        # Plumber-specific responses
        "Plumber": {
            "cost": (
                "Water issues get expensive fast if not fixed right. A leak that seems small can cost thousands in water damage. "
                "We're upfront about pricing and only do what's necessary. The team will walk through options at the site."
            ),
            "timeline": (
                "Most drain issues resolve in an hour or two. Water heaters take 3–4 hours. We'll confirm timing before we start."
            ),
            "warranty": (
                "Every repair comes with our guarantee. If something we fixed leaks within a year, we come back—no charge."
            ),
        },
        # Electrician-specific responses
        "Electrician": {
            "cost": (
                "Electrical work is regulated and code-required because it's a safety issue. Cutting corners on price means "
                "cutting corners on safety. Our pricing reflects code compliance and inspections. You're not just paying us—"
                "you're paying for the safety of your home."
            ),
            "timeline": (
                "Simple outlet repairs take 30 minutes. Panel upgrades take 1–2 days. We'll give you exact timing after inspection."
            ),
            "warranty": (
                "All work meets code and is inspected. Our labor is guaranteed for 1 year. Safety is not negotiable."
            ),
        },
        # Roofing-specific responses
        "Roofing": {
            "cost": (
                "Roofing is one of the biggest investments on a home because it lasts 20+ years and protects everything underneath. "
                "A cheap roof fails early and costs more to replace again. We quote fair prices for materials and craftsmanship that last. "
                "Our inspection will show exactly what you need."
            ),
            "timeline": (
                "Small repairs take a few hours. Full replacements take 1–3 days depending on size. We'll schedule around your life."
            ),
            "warranty": (
                "Shingles come with manufacturer warranties. Our workmanship is guaranteed for life. If something fails because of our work, we fix it."
            ),
        },
        # Pest Control-specific responses
        "Pest Control": {
            "cost": (
                "The cost of pests—damage, health risks, lost peace of mind—adds up fast. Prevention is way cheaper than dealing with "
                "an infestation. Our plans are built to stop problems before they start."
            ),
            "timeline": (
                "Initial treatment is usually done in a single visit. Follow-ups are part of quarterly plans. We'll explain the timeline for results."
            ),
            "warranty": (
                "Our treatments come with a guarantee. If pests return between visits, we come back at no charge."
            ),
        },
        # Water Damage Restoration-specific responses
        "Water Damage Restoration": {
            "cost": (
                "Speed matters with water damage—the longer it sits, the more damage spreads and the more it costs to fix. "
                "Our fast response and thorough drying save you money overall. We'll assess scope and cost during the emergency visit."
            ),
            "timeline": (
                "We're on-site within 60 minutes, 24/7. Drying typically takes 3–7 days depending on how much water we're dealing with. "
                "We'll keep you updated every step."
            ),
            "warranty": (
                "Our mitigation is guaranteed. If mold appears after we've dried and tested, we cover remediation."
            ),
        },
        # Landscaping-specific responses
        "Landscaping": {
            "cost": (
                "Good landscaping design saves water and maintenance costs over time. A cheap install fails and needs rework. "
                "We focus on designs that work for the climate and your budget. The team will show options during the design visit."
            ),
            "timeline": (
                "Design takes 1–2 weeks. Installation depends on scope—small projects 1–2 days, large ones 1–2 weeks. We'll outline the timeline upfront."
            ),
            "warranty": (
                "Plants come with establishment guarantees. If trees or shrubs don't take, we replace them. Our install work is guaranteed for 1 year."
            ),
        },
        # Tree Service-specific responses
        "Tree Service": {
            "cost": (
                "Tree work is specialized and can be risky if not done right. Cutting corners invites liability, damage, or injury. "
                "Our pricing reflects professional training and insurance. The team will walk you through the work and cost during the assessment."
            ),
            "timeline": (
                "Small trimming takes a few hours. Removals take half a day to a day depending on tree size. We'll give exact timing after we see the tree."
            ),
            "warranty": (
                "Our crew is ISA Certified Arborist-led. Work is guaranteed, and we carry full liability insurance."
            ),
        },
        # Cleaning Services-specific responses
        "Cleaning Services": {
            "cost": (
                "Your time is valuable. Outsourcing cleaning frees you up for higher-value activities. Our pricing is fair for professional, reliable service. "
                "Same team every visit, so continuity matters."
            ),
            "timeline": (
                "Regular house cleaning takes 2–3 hours depending on home size. Deep cleans take 4–6 hours. We'll nail down the exact time on your first visit."
            ),
            "warranty": (
                "We back our work. If you're not satisfied with any visit, we'll come back and make it right."
            ),
        },
    }

    @classmethod
    def get_response(cls, objection_type: str, industry: str, context: Optional[dict] = None) -> str:
        """Get a professional response to an objection.

        Args:
            objection_type: Objection key (e.g. 'cost', 'timeline', 'warranty')
            industry: Industry (e.g. 'HVAC', 'Plumber')
            context: Optional dict with 'business_name', 'services', etc. for personalization

        Returns:
            Professional response text
        """
        context = context or {}

        # Try industry-specific response first, fall back to default
        industry_responses = cls._OBJECTIONS.get(industry, {})
        response = industry_responses.get(objection_type)

        if not response:
            # Fall back to default response for this objection type
            response = cls._OBJECTIONS["default"].get(objection_type, cls._default_fallback(objection_type))

        # Personalize if context provided
        if context.get("business_name"):
            response = response.replace("{business_name}", context["business_name"])
        if context.get("services"):
            services_str = ", ".join(context["services"][:2])
            response = response.replace("{services}", services_str)

        return response

    @classmethod
    def get_objection_types(cls, industry: str) -> list[str]:
        """Get the list of known objection types for an industry.

        Returns a combined set from industry-specific and default objections.
        """
        industry_responses = cls._OBJECTIONS.get(industry, {})
        default_responses = cls._OBJECTIONS["default"]

        objection_types = set()
        objection_types.update(industry_responses.keys())
        objection_types.update(default_responses.keys())

        return sorted(objection_types)

    @staticmethod
    def _default_fallback(objection_type: str) -> str:
        """Fallback response for unknown objection types."""
        return (
            "That's a great question. Our team is committed to finding the best solution for your situation. "
            "We'll discuss this thoroughly during the site visit. Feel free to ask any questions when we arrive."
        )

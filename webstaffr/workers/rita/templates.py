"""Review request and response templates for Rita.

No fabrication: templates use only real tenant data and real review content.
Never generate fake reviews, ratings, or reviewers. Never invent statistics.

Templates are gated on actual tenant data:
- Review request: only sent if tenant exists
- Response drafts: only reference review text actually received (never invented)
"""

from __future__ import annotations


def render_review_request_sms(
    contact_name: str | None,
    business_name: str,
    review_link: str = "https://g.co/reviews",
) -> str:
    """SMS template for review request."""
    name_or_there = contact_name or "there"
    return f"Hi {name_or_there}, thanks for choosing {business_name}! Please leave us a review: {review_link}"


def render_review_request_email(
    contact_name: str | None,
    business_name: str,
    review_link: str = "https://g.co/reviews",
) -> tuple[str, str]:
    """Email template for review request. Returns (subject, body)."""
    subject = "We'd love to hear from you!"
    name_or_friend = contact_name or "friend"
    body = f"""Hi {name_or_friend},

Thank you for choosing {business_name}. Your feedback helps us improve.

Please share your experience here: {review_link}

Thanks!
"""
    return (subject, body)


def draft_positive_response(review_text: str, business_name: str) -> str:
    """Draft response for positive review (rating >= 4)."""
    return f"""Thank you so much for taking the time to share your feedback! We truly appreciate your kind words and are thrilled you had a great experience with {business_name}. We look forward to serving you again soon!"""


def draft_neutral_response(review_text: str, business_name: str) -> str:
    """Draft response for neutral review (rating == 3)."""
    return f"""Thank you for your feedback! We're glad we could help with your recent service. We'd love to hear more about what would have made your experience even better. Please feel free to reach out to us directly so we can improve. We appreciate the opportunity to serve you at {business_name}!"""


def draft_negative_response(review_text: str, business_name: str) -> str:
    """Draft response for negative review (rating <= 2). REQUIRES founder approval before posting."""
    prefix = "*** NEGATIVE REVIEW - PENDING YOUR APPROVAL BEFORE POSTING ***\n\n"
    response = f"""We're truly sorry to hear that your experience with {business_name} didn't meet your expectations. We take your feedback seriously and would like the opportunity to make things right. Please reach out to us directly at your earliest convenience so we can discuss how we can better serve you in the future. Your satisfaction is important to us."""
    return prefix + response


def select_response_template(rating: int, review_text: str, business_name: str) -> tuple[str, bool]:
    """Select and draft appropriate response based on review rating.

    Returns:
        Tuple of (response_text, requires_approval).
        - Positive (4-5): auto-drafts, no approval needed
        - Neutral (3): auto-drafts, no approval needed
        - Negative (1-2): auto-drafts, REQUIRES approval before posting
    """
    if rating >= 4:
        return (draft_positive_response(review_text, business_name), False)
    elif rating == 3:
        return (draft_neutral_response(review_text, business_name), False)
    else:  # rating <= 2
        return (draft_negative_response(review_text, business_name), True)

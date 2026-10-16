"""Leo: Lead Coordinator AI worker.

Instant follow-up on every lead within 2 minutes. Scores leads using AOKAI
100-point rubric, routes to call-led or email-led sequences, sends first touch
via GHL messaging.

See docs/WORKERS_LEO_DESIGN.md for full architecture.
"""

from __future__ import annotations

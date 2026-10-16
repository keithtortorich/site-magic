"""Rita -- the Reputation Manager AI worker.

Automates review request sending and response management for completed jobs.
Target: 100% review response rate, request sent within 24h of job completion.

Rita's endpoint (/webhooks/ghl/job_completed) is a sibling route to Angel's
(/webhooks/ghl, /chat, /book), built using the same composition-root pattern,
dependency injection, and tenant isolation.
"""

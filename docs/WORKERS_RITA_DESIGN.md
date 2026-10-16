# Rita: Reputation Manager AI Worker

## Overview

Rita automates review request sending and response management for completed jobs. Goal: 100% review response rate, requests sent within 24 hours of job completion.

Rita is a sibling worker to Angel, built using the same composition-root pattern (`webstaffr/app.py`), dependency-injection architecture, and tenant-isolation model.

## Triggering Events

### Job Completion Webhook (GHL)
- **Source**: GoHighLevel workflow webhook when a job/appointment transitions to "completed"
- **Endpoint**: `POST /webhooks/ghl/job_completed`
- **Payload**: `GHLJobCompletedEvent` (minimal shape, fields we actually use)
  - `tenant_id`: Text, required, validated as valid Tenant
  - `event_type`: Text, always "job_completed" (or similar; supports future extensions)
  - `job_id`: Optional text (GHL appointment ID for cross-referencing)
  - `contact_id`: Text, required (GHL contact ID for review request routing)
  - `contact_name`: Optional text (customer name, used in template personalization)
  - `contact_phone`: Optional text (SMS destination if SMS review request chosen)
  - `contact_email`: Optional text (email destination if email review request chosen)

### Public API for Draft Review Responses
- **Endpoint**: `POST /workers/rita/draft-response` (internal only, no CORS)
- **Purpose**: Return a templated response to a review received from external review platform
- **Access**: Server-to-server or founder dashboard (not browser-facing)
- **Payload**: `DraftResponseRequest`
  - `tenant_id`: Text
  - `review_id`: Text (external platform review identifier)
  - `review_text`: Text (full review body)
  - `review_rating`: Integer (1-5 stars, or similar scale native to platform)
  - `review_source`: Text (Google, Yelp, etc. — for template selection)

## Data Model

### New Tables (migrations)

#### review_requests
Tracks each review request sent to a customer after job completion.

```sql
CREATE TABLE review_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    ghl_job_id TEXT,  -- appointment/event ID in GHL
    contact_id TEXT NOT NULL,  -- GHL contact ID
    contact_name TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    review_source TEXT,  -- "google", "native", etc.; determines platform
    request_method TEXT NOT NULL,  -- "sms", "email"
    requested_at TEXT NOT NULL,  -- ISO 8601 timestamp
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, responded, failed
    ghl_synced INTEGER NOT NULL DEFAULT 0,  -- 0/1: whether we sent the GHL SMS/email
    created_at TEXT NOT NULL
);

CREATE INDEX idx_review_requests_tenant ON review_requests(tenant_id);
CREATE INDEX idx_review_requests_contact ON review_requests(contact_id);
CREATE INDEX idx_review_requests_status ON review_requests(status);
```

#### review_responses
Incoming reviews from external platforms and our drafted responses.

```sql
CREATE TABLE review_responses (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    request_id INTEGER REFERENCES review_requests(request_id),
    review_source TEXT NOT NULL,  -- Google, Yelp, etc.
    external_review_id TEXT,  -- platform's own ID
    review_rating INTEGER,  -- 1-5 stars
    review_text TEXT,
    reviewer_name TEXT,
    received_at TEXT,  -- ISO 8601, from platform if available
    response_status TEXT NOT NULL DEFAULT 'pending_draft',
    -- pending_draft: awaiting founder review
    -- approved: founder approved, ready to post
    -- posted: response sent to review platform
    -- failed: posting failed
    response_text TEXT,
    response_approved_at TEXT,
    response_posted_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_review_responses_tenant ON review_responses(tenant_id);
CREATE INDEX idx_review_responses_request ON review_responses(request_id);
CREATE INDEX idx_review_responses_status ON review_responses(response_status);
```

## Data Flow

### 1. Job Completion → Review Request Sent

```
GHL Workflow (job marked complete)
           ↓
POST /webhooks/ghl/job_completed
           ↓
Rita validates event (tenant exists, contact_id present)
           ↓
Load tenant config (review platform, SMS/email preference)
           ↓
Build review request SMS/email from template
           ↓
Call GHL to send SMS/email OR call review platform API directly
           ↓
Log review_request record (status='pending', ghl_synced=1 if sent)
           ↓
Return 200 OK
```

### 2. Incoming Review → Draft Response

```
[Future enhancement: cron or webhook from review platform]
           ↓
Review received (Google, Yelp, etc.)
           ↓
POST /workers/rita/draft-response
           ↓
Rita loads review_request (if exists)
           ↓
Select response template based on rating (positive/neutral/negative)
           ↓
Draft response text (never fabricating, only using real tenant data)
           ↓
Log review_response record (response_status='pending_draft', response_text=drafted)
           ↓
Return drafted response to caller
           ↓
[Founder reviews in dashboard or via direct DB query]
           ↓
MANUAL: founder approves response (updates response_approved_at)
           ↓
[Future: scheduled task posts approved responses to platform]
```

### 3. Response Approval → Posting

```
[Post-MVP: scheduled task or manual trigger]
           ↓
Query all review_responses where response_status='approved' and response_posted_at IS NULL
           ↓
For each: call review platform API to post response_text
           ↓
Update response_posted_at, response_status='posted' on success
           ↓
Log failed responses with error message, retry next cycle
```

## Integration Points

### GHL Integration (via existing GHLClient)
Rita reuses the `GHLClient` protocol already in place for Angel:
- Extends `GHLClient` protocol with two new methods:
  - `send_sms(contact_id: str, message: str) -> dict`: Send SMS to contact
  - `send_email(contact_id: str, subject: str, body: str) -> dict`: Send email to contact
  - OR use existing GHL workflow/messaging APIs exposed through the standard `_request()` method

Actually, to avoid modifying the Angel-owned GHLClient protocol, Rita will:
- **Use GHLClient.log_note()** to log outgoing review requests as notes on the contact record (audit trail)
- **Implement its own ReviewPlatformClient protocol** (Google, Yelp, etc.) with a NullReviewPlatformClient safe default
- Defer SMS/email sending to a future review-platform specific integration (Google has its own review-request API; Yelp differs)

For MVP, Rita's review request will be: call `ghl_client.log_note(contact_id, "Review request sent via SMS/email on [date]")` and emit the record to review_requests table. Actual SMS/email sending is gated on tenant configuration (post-MVP enhancement).

### Review Platform Integration (Protocol + Null)

**ReviewPlatformClient Protocol:**
```python
class ReviewPlatformClient(Protocol):
    def get_recent_reviews(self, tenant_id: str, since: str) -> list[dict]: ...
    def post_review_response(self, review_id: str, response_text: str) -> dict: ...
```

**NullReviewPlatformClient** (default, no-op, logs to memory for tests):
```python
class NullReviewPlatformClient:
    def get_recent_reviews(self, tenant_id: str, since: str) -> list[dict]:
        return []
    def post_review_response(self, review_id: str, response_text: str) -> dict:
        return {"status": "logged_in_memory"}
```

For MVP: both methods are no-ops. The webhook from external platform will be implemented post-MVP when a real review platform is chosen and configured.

## Template System

### Review Request Templates
**No fabrication rule applies strictly here**: never generate fake reviews, never invent ratings, never include false statistics.

Templates are stored in `workers/rita/templates.py`:

**1. Default Request (sent via SMS or email)**
- Personalized with customer name if available
- Thank-you for business + explicit request for review
- Link to review platform (e.g., Google Business Profile, Yelp)
- No fake reviews or ratings visible to customer

Example SMS:
```
Hi {name}, thanks for choosing {business_name}! Please leave us a review on Google: [link]
```

Example Email:
```
Subject: We'd love to hear from you!

Hi {name},

Thank you for choosing {business_name}. Your feedback helps us improve.

Please share your experience here: [review_link]

Thanks!
```

### Response Templates
**Positive Review (rating >= 4):**
- Thank-you for kind words
- Reinforce one specific point from the review if safe to do so
- Offer next-step (return visit, referral, etc.)
- Include business name, no fabricated credentials

**Neutral Review (rating == 3):**
- Acknowledge feedback
- Ask specific follow-up question to understand gaps
- Invite direct contact for resolution
- No defensive tone

**Negative Review (rating <= 2):**
- Acknowledge concern without disputing
- Flag for founder review (auto-drafted but not posted)
- Do NOT post automatically
- Draft includes: "This response is pending your approval. Review below before posting."
- Suggest direct outreach over public response

## API Contract

### POST /webhooks/ghl/job_completed

**Request:**
```json
{
  "tenant_id": "acme",
  "event_type": "job_completed",
  "job_id": "ghl_appt_123",
  "contact_id": "ghl_contact_456",
  "contact_name": "Alice Smith",
  "contact_phone": "+15551234567",
  "contact_email": "alice@example.com"
}
```

**Response (200 OK):**
```json
{
  "status": "review_request_logged",
  "request_id": 42,
  "contact_id": "ghl_contact_456"
}
```

**Errors:**
- `400 Bad Request`: Invalid tenant_id, missing contact_id
- `429 Too Many Requests`: Rate-limited (same per-tenant rate limit as Angel)
- `503 Service Unavailable`: DB connection failed

**Headers:**
- No CORS headers (server-to-server only)
- Supports `X-Webhook-Secret` header for signature verification (optional, same pattern as Angel's `/webhooks/ghl`)

### POST /workers/rita/draft-response

**Request:**
```json
{
  "tenant_id": "acme",
  "review_id": "external_review_123",
  "review_text": "Great service, highly recommend!",
  "review_rating": 5,
  "review_source": "google"
}
```

**Response (200 OK):**
```json
{
  "response_id": 99,
  "review_id": "external_review_123",
  "response_status": "pending_draft",
  "response_text": "[drafted positive response]",
  "requires_approval": false
}
```

For negative reviews:
```json
{
  "response_id": 100,
  "review_id": "external_review_124",
  "response_status": "pending_draft",
  "response_text": "[drafted response, flagged for review]",
  "requires_approval": true,
  "note": "Negative review detected. Response drafted but pending your approval before posting."
}
```

**Errors:**
- `400 Bad Request`: Invalid tenant_id, malformed review data
- `404 Not Found`: Review not found (if looking up existing request)
- `503 Service Unavailable`: DB connection failed

## Error Handling

### GHL Sync Failures
- Log error, set `ghl_synced=0` in review_request record
- Optionally: schedule retry (post-MVP)
- Do not block webhook response (fail open)

### DB Failures
- Log exception type only (never the connection string)
- Return HTTP 503 to caller
- Same pattern as Angel's existing DB error handling

### Missing Credentials
- Review platform API keys not configured → NullReviewPlatformClient returns empty list
- Fails open (no reviews fetched, but no crash)
- Log warning only on first use

## Testing Strategy

### Unit Tests
- Template rendering (positive/neutral/negative, no fabrication)
- Review request record creation and validation
- Response draft logic (rating thresholds, requires_approval flag)

### Integration Tests
- Job completion webhook → review_request record created
- Negative review webhook → response drafted with requires_approval=true
- Positive review webhook → response drafted with requires_approval=false
- Tenant isolation (tenant A's reviews not visible to tenant B)
- Rate limiting applied same as Angel (/webhooks/ghl route)

### Round-Trip Tests
- Full flow: job_completed → request logged → draft-response called → response record created

## Security & Compliance

**No Fabrication:** Review text, ratings, and reviewer identities are never generated. Only real incoming data is stored and only real tenant data is used in responses.

**Tenant Isolation:** Every query filters by tenant_id. review_requests and review_responses tables both have tenant_id as a required foreign key and indexed.

**CORS Scoping:** `/webhooks/ghl/job_completed` is server-to-server only (not added to `_CORS_SCOPED_PATHS` in app.py). `/workers/rita/draft-response` is also internal, no CORS.

**Webhook Verification:** Optional `X-Webhook-Secret` header support (same SharedSecretVerifier pattern as Angel's `/webhooks/ghl`).

**No Secrets in Logs:** Connection errors log exception type only, never detail or connection strings.

## Future Enhancements (Post-MVP)

1. **Scheduled Review Fetching**: Cron task that polls review platforms for new reviews and creates review_response records
2. **Scheduled Response Posting**: Cron task that posts approved responses to platforms
3. **SMS/Email Review Request**: Integrate with Twilio or GHL's native SMS/email to send actual review request texts
4. **Dashboard**: Founder-facing UI to approve/reject responses before posting
5. **Multi-Platform Support**: Real integrations with Google, Yelp, Trustpilot, etc. (currently stubbed with NullReviewPlatformClient)
6. **Analytics**: Review volume, response rate, sentiment trends over time
7. **Automatic Positive Response Posting**: Only auto-post 5-star responses; require approval for all others

## Composition Root Integration

Rita's router is included in `webstaffr/app.py` as a sibling to Angel:

```python
from .workers.rita.router import create_rita_router

app.include_router(
    create_rita_router(
        db_path=db_path,
        ghl_client=ghl_client,
        ghl_webhook_verifier=ghl_webhook_verifier,  # same verifier as Angel
    )
)
```

No new dependencies added. No changes to Angel's code or other workers.

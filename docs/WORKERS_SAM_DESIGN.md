# Sam: The Sales Consultant AI Worker

## Overview

Sam is WebStaffr's second AI-employee worker (sibling to Angel, the AI receptionist). Sam generates quotes, handles common objections, and drives quote-to-booking conversion.

**Core job:** Accept high-intent leads → generate professional, data-backed quotes → handle objections → drive booking.

**Target:** 50% of quotes sent automatically within 24h of lead intake, quote-to-booking conversion tracked per industry.

## Architecture

### Triggering Events

1. **High-AOKAI lead from Leo** (future: Leo is the lead-scorer service)
   - Endpoint: `/quotes/generate` (POST)
   - Payload: lead data (contact_id, name, phone, business context from intake/chat)
   - Sam pulls service scope from GHL contact notes, intake submission, or chat history
   - Auto-generates and sends quote via GHL email

2. **Explicit "request quote" intent from Angel chat**
   - Within `/chat` turn: Angel detects "I'd like a quote" → routes to Sam via in-process call
   - Same quote generation → email via GHL
   - Angel confirms: "I've sent you a quote to [email], check it in a few minutes"

### Quote Generation Flow

```
Lead input (scope, industry, location) 
  ↓
Apply trade-specific pricing presets (trade_presets.py)
  ↓
Adjust for complexity/urgency multipliers
  ↓
Generate estimate range (low-high)
  ↓
Add caveats ("subject to site inspection")
  ↓
Build email template (professional, not salesy)
  ↓
Store quote record (local DB)
  ↓
Send via GHL (if configured) or store for manual send
  ↓
Return quote ID to caller
```

### Data Flow

1. **Input sources:**
   - GHL contact record (contact_id, name, phone, email, custom fields)
   - Intake submission (industry, service_area, services)
   - Chat context (from Angel: what services the customer mentioned)

2. **Pricing data:**
   - `webstaffr/trade_presets.py` defines per-trade service ranges
   - No hardcoded specifics; always use ranges + caveats
   - Missing data → "Contact for custom quote" fallback

3. **Output:**
   - Quote object: id, tenant_id, contact_id, estimated_range_low, estimated_range_high, caveat, email_template, created_at, status (pending/sent/accepted/declined)
   - Quote email sent to contact (via GHL or local capture)
   - Quote record stored in local DB for tracking

### Objection Handling

Common objections per trade (cost, timeline, warranty, availability) with professional, educational responses.

```
Objection detected (explicit mention or inferred from chat)
  ↓
Look up trade-specific response template
  ↓
Personalize with business name, services mentioned
  ↓
Return response to Angel (if in-chat) or store for sales rep
  ↓
If objection unresolved after N turns, escalate to human
```

### Booking Flow

1. **Quote accepted (via email link or explicit consent)**
   - Calls `/book` (Angel's existing endpoint)
   - Creates appointment, syncs to GHL
   - Logs booking source as "quote_id: {quote_id}"

2. **Quote declined/expired**
   - Mark quote as declined in DB
   - Log reason (if provided)
   - Trigger follow-up sequence (future: in-app marketing coordinator)

## API Contract

### POST /quotes/generate
**Generates and sends a quote.**

```json
{
  "tenant_id": "string",
  "contact_id": "string (GHL)",
  "contact_name": "string",
  "contact_phone": "string",
  "contact_email": "string",
  "service_scope": "string (free-text description of what they need)",
  "industry": "string (optional, from intake if available)",
  "location": "string (optional)",
  "urgency": "routine|urgent|emergency (optional, default: routine)"
}
```

Response:
```json
{
  "quote_id": "uuid",
  "tenant_id": "string",
  "contact_id": "string",
  "estimated_range_low": 150,
  "estimated_range_high": 800,
  "caveat": "Final quote after site inspection",
  "email_sent": true,
  "created_at": "2026-07-28T15:30:00Z"
}
```

### GET /quotes/{quote_id}
**Retrieve a quote.**

Response:
```json
{
  "quote_id": "uuid",
  "tenant_id": "string",
  "contact_id": "string",
  "estimated_range_low": 150,
  "estimated_range_high": 800,
  "caveat": "Final quote after site inspection",
  "status": "pending|sent|accepted|declined",
  "created_at": "2026-07-28T15:30:00Z",
  "sent_at": "2026-07-28T15:32:00Z (or null)",
  "accepted_at": "2026-07-28T16:00:00Z (or null)"
}
```

### POST /quotes/{quote_id}/accept
**Accept a quote and initiate booking.**

```json
{
  "tenant_id": "string",
  "preferred_time": "2026-08-05T10:00:00Z (optional)"
}
```

Response:
```json
{
  "quote_id": "uuid",
  "appointment_id": "int",
  "status": "accepted",
  "appointment_scheduled": true,
  "accepted_at": "2026-07-28T16:00:00Z"
}
```

## Interfaces & Protocols

### GHLClient Extension (Existing Protocol)
Sam adds one method to the existing `GHLClient` protocol:
```python
def send_quote_email(self, contact_id: str, quote_id: str, email_body: str, subject: str) -> dict: ...
```

### TradePresetAccessor (New Protocol)
```python
class TradePresetAccessor(Protocol):
    def get_pricing_range(self, industry: str, service: str) -> tuple[float, float]: ...
    # Returns (low, high) for the service in the trade
    # Raises ValueError if industry/service not found
```

### ObjectionHandler (New Protocol)
```python
class ObjectionHandler(Protocol):
    def get_response(self, objection: str, trade: str, context: dict) -> str: ...
    # Returns professional response template
    # context may include business_name, services_mentioned, etc.
```

## Database Schema

### quotes table
```sql
CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY,  -- uuid
  tenant_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT,
  service_scope TEXT NOT NULL,
  industry TEXT,
  estimated_range_low REAL NOT NULL,
  estimated_range_high REAL NOT NULL,
  caveat TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending, sent, accepted, declined
  email_template TEXT,  -- HTML body of the sent email
  created_at TEXT NOT NULL,
  sent_at TEXT,
  accepted_at TEXT,
  appointment_id INTEGER,  -- foreign key to appointments.id when accepted
  FOREIGN KEY(tenant_id) REFERENCES tenants(id),
  FOREIGN KEY(appointment_id) REFERENCES appointments(id)
)

-- All queries tenant-scoped:
CREATE INDEX idx_quotes_tenant_status ON quotes(tenant_id, status);
CREATE INDEX idx_quotes_contact ON quotes(tenant_id, contact_id);
```

## Modules

### `workers/sam/router.py`
FastAPI router with the three POST/GET endpoints above.
- Thin request validation, route to protocol/service layer
- Tenant isolation enforced per endpoint
- CORS: POST routes carry no CORS headers (server-to-server only)

### `workers/sam/protocol.py`
Abstract interfaces:
- `GHLQuoteClient`: extends existing GHLClient with `send_quote_email()`
- `TradePresetAccessor`: get per-trade pricing ranges
- `ObjectionHandler`: lookup and render objection responses

Null implementations for test/unconfigured environments.

### `workers/sam/client.py`
**GHL integration:**
- Wraps existing GHLClient
- Adds `send_quote_email()`: constructs email, POSTs to GHL API
- Implements quote-sending via GHL's contact email field
- Error handling: quote saved locally if GHL unavailable, synced when back

### `workers/sam/pricing.py`
**Quote generation logic:**
- `generate_quote()` function
- Input: service_scope (string), industry, location, urgency
- Process:
  1. Parse service_scope to infer specific services mentioned
  2. Look up trade_presets.py ranges for each service
  3. Apply multipliers: urgency (1.0-1.5x), complexity (0.8-1.3x), location premium (0.9-1.2x)
  4. Compute final low/high range
  5. Generate caveat text (always includes "subject to site inspection")
  6. Return pricing data structure
- Never fabricates: if trade/service unknown, returns placeholder "Contact for quote"

### `workers/sam/objections.py`
**Objection handling:**
- Per-trade objection library (cost, timeline, warranty, etc.)
- Response templates: professional, educational tone (not pushy)
- Context-aware personalization (business name, services mentioned)
- Escalation logic: if objection repeated 2+ times, flag for human review
- No promise-making: caveats always present ("our team will discuss this during the site visit")

### `workers/sam/quote_repository.py`
**Quote persistence:**
- Same pattern as `workers/angel/booking.py`
- Raw SQL via `webstaffr/db.py`, `?` placeholders
- Methods:
  - `create_quote(...)` → stores and returns quote_id
  - `get_quote(quote_id, tenant_id)` → fetch (tenant-scoped)
  - `update_quote_status(quote_id, status, ...)` → mark sent/accepted/declined
  - `list_quotes_by_contact(contact_id, tenant_id)` → history
- All queries tenant-scoped

## Error Handling

1. **GHL unavailable:**
   - Save quote locally
   - Return quote_id to caller (success)
   - Background sync (future) or manual escalation when GHL comes back

2. **Pricing data missing:**
   - Return "Contact for custom quote" caveat
   - Range: (0, 0) or NULL
   - Still create quote record (don't fail)

3. **Invalid input:**
   - Return 400 with validation errors (same pattern as Angel)

4. **Tenant not found:**
   - Return 400 InvalidTenantError (same as Angel)

5. **Objection requires escalation:**
   - Log in notes
   - Flag quote status as needs_human_review
   - Trigger notification to sales rep (future)

## Testing Strategy

### Unit Tests (`tests/test_sam_*.py`)

1. **test_quote_generation.py**
   - Happy path: scope → pricing → range calculation
   - Edge cases: missing trade, unknown service, extreme urgency
   - Multiplier math verified for various inputs
   - Caveats always present

2. **test_objection_handling.py**
   - Objection lookup and response rendering
   - Context personalization
   - Escalation after N repeated objections

3. **test_quote_repository.py**
   - Create, read, update, tenant isolation
   - Status transitions (pending → sent → accepted)

4. **test_sam_router.py**
   - Full round-trip: POST /quotes/generate → quote created + email sent
   - GET /quotes/{id} returns correct data
   - POST /quotes/{id}/accept → appointment created
   - Tenant isolation verified
   - Error cases (invalid tenant, missing fields)

### Integration Tests

- Lead intake → Sam quote generation → Angel handles objection → booking
- Quote email body never contains hardcoded prices (ranges + caveats only)
- GHL unavailable scenario: quote saved, synced when available

## Constraints

- **No fabrication:** Ranges come from trade_presets only; no inventing specific numbers
- **Caveats always present:** Every quote includes "subject to site inspection" or equivalent
- **Tenant isolation:** Every query scoped to tenant_id
- **No new dependencies:** Use stdlib only (same as Angel)
- **CORS:** POST routes carry no CORS headers
- **Error resilience:** GHL down → local save → sync later
- **Null defaults:** Unconfigured GHL → NullGHLClient, no network calls

## Out of Scope (Post-MVP)

- Marketing Coordinator follow-up sequences (separate worker)
- SMS/email objection handling (future D4 vendor)
- Multi-language quote templates
- Dynamic pricing based on historical job costs per tenant
- Scheduling/appointment availability checking
- A/B testing quote formats
- Quote expiry enforcement (created_at age-based)

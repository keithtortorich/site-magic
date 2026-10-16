CREATE TABLE site_magic_facts (
    fact_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified', 'unverified', 'rejected', 'superseded')),
    verified_by TEXT,
    verified_at TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (verified_by) REFERENCES customer_users(user_id) ON DELETE SET NULL
);

CREATE INDEX idx_site_magic_facts_tenant_status
    ON site_magic_facts(tenant_id, status, created_at DESC);

CREATE TABLE site_magic_plans (
    plan_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'proposed', 'approved', 'superseded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_site_magic_plans_tenant_updated
    ON site_magic_plans(tenant_id, updated_at DESC);

CREATE TABLE site_magic_plan_versions (
    plan_version_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    content_json TEXT NOT NULL,
    fact_snapshot_json TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    fact_snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'proposed', 'approved', 'superseded')),
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (plan_id) REFERENCES site_magic_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES customer_users(user_id) ON DELETE SET NULL,
    UNIQUE (tenant_id, plan_id, version)
);

CREATE INDEX idx_site_magic_plan_versions_tenant_plan
    ON site_magic_plan_versions(tenant_id, plan_id, version DESC);

CREATE TABLE site_magic_approvals (
    approval_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    fact_snapshot_hash TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES site_magic_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (approved_by) REFERENCES customer_users(user_id) ON DELETE RESTRICT,
    UNIQUE (tenant_id, plan_id, plan_version)
);

CREATE INDEX idx_site_magic_approvals_tenant_time
    ON site_magic_approvals(tenant_id, approved_at DESC);

CREATE TABLE site_magic_build_requests (
    build_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    fact_snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'started', 'failed', 'preview_ready', 'blocked')),
    requested_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (approval_id) REFERENCES site_magic_approvals(approval_id) ON DELETE RESTRICT,
    FOREIGN KEY (plan_id) REFERENCES site_magic_plans(plan_id) ON DELETE RESTRICT,
    FOREIGN KEY (requested_by) REFERENCES customer_users(user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_site_magic_build_requests_tenant_time
    ON site_magic_build_requests(tenant_id, created_at DESC);

CREATE TABLE site_magic_previews (
    preview_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    preview_locator TEXT NOT NULL,
    artifact_manifest_json TEXT NOT NULL,
    rendered_evidence_json TEXT NOT NULL,
    trace_manifest_json TEXT NOT NULL,
    quality_report_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verifying', 'ready', 'blocked')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (build_id) REFERENCES site_magic_build_requests(build_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    UNIQUE (tenant_id, build_id)
);

CREATE INDEX idx_site_magic_previews_tenant_time
    ON site_magic_previews(tenant_id, created_at DESC);

CREATE TABLE site_magic_revisions (
    revision_id TEXT PRIMARY KEY,
    preview_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    request_text TEXT NOT NULL,
    change_class TEXT NOT NULL CHECK (change_class IN ('presentation', 'semantic')),
    expected_impact_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'applied', 'rejected')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (preview_id) REFERENCES site_magic_previews(preview_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES customer_users(user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_site_magic_revisions_tenant_time
    ON site_magic_revisions(tenant_id, created_at DESC);

CREATE TABLE site_magic_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    preview_id TEXT NOT NULL,
    build_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    artifact_manifest_json TEXT NOT NULL,
    trace_manifest_json TEXT NOT NULL,
    quality_report_json TEXT NOT NULL,
    accepted_by TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    FOREIGN KEY (preview_id) REFERENCES site_magic_previews(preview_id) ON DELETE RESTRICT,
    FOREIGN KEY (build_id) REFERENCES site_magic_build_requests(build_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (accepted_by) REFERENCES customer_users(user_id) ON DELETE RESTRICT,
    UNIQUE (tenant_id, preview_id)
);

CREATE INDEX idx_site_magic_checkpoints_tenant_time
    ON site_magic_checkpoints(tenant_id, accepted_at DESC);

CREATE TABLE site_magic_releases (
    release_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'publishing', 'published', 'failed', 'rolled_back')),
    public_locator TEXT,
    requested_by TEXT NOT NULL,
    failure_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT,
    FOREIGN KEY (checkpoint_id) REFERENCES site_magic_checkpoints(checkpoint_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (requested_by) REFERENCES customer_users(user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_site_magic_releases_tenant_time
    ON site_magic_releases(tenant_id, created_at DESC);

CREATE TABLE site_magic_active_releases (
    tenant_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    activated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (release_id) REFERENCES site_magic_releases(release_id) ON DELETE RESTRICT,
    FOREIGN KEY (checkpoint_id) REFERENCES site_magic_checkpoints(checkpoint_id) ON DELETE RESTRICT
);

CREATE TABLE site_magic_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    aggregate_sequence INTEGER NOT NULL CHECK (aggregate_sequence > 0),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    correlation_id TEXT NOT NULL,
    causation_id TEXT,
    idempotency_key TEXT NOT NULL,
    payload_schema_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    prev_event_hash TEXT,
    event_hash TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, aggregate_sequence)
);

CREATE INDEX idx_site_magic_events_tenant_time
    ON site_magic_events(tenant_id, occurred_at DESC);

CREATE INDEX idx_site_magic_events_aggregate
    ON site_magic_events(tenant_id, aggregate_type, aggregate_id, aggregate_sequence);

CREATE TRIGGER site_magic_events_immutable_update
BEFORE UPDATE ON site_magic_events
BEGIN
    SELECT RAISE(ABORT, 'site_magic_events is append-only');
END;

CREATE TRIGGER site_magic_events_immutable_delete
BEFORE DELETE ON site_magic_events
BEGIN
    SELECT RAISE(ABORT, 'site_magic_events is append-only');
END;

CREATE TRIGGER site_magic_approvals_immutable_update
BEFORE UPDATE ON site_magic_approvals
BEGIN
    SELECT RAISE(ABORT, 'site_magic_approvals is immutable');
END;

CREATE TRIGGER site_magic_approvals_immutable_delete
BEFORE DELETE ON site_magic_approvals
BEGIN
    SELECT RAISE(ABORT, 'site_magic_approvals is immutable');
END;

CREATE TRIGGER site_magic_plan_versions_immutable_content
BEFORE UPDATE ON site_magic_plan_versions
WHEN OLD.plan_version_id IS NOT NEW.plan_version_id
  OR OLD.plan_id IS NOT NEW.plan_id
  OR OLD.tenant_id IS NOT NEW.tenant_id
  OR OLD.version IS NOT NEW.version
  OR OLD.content_json IS NOT NEW.content_json
  OR OLD.fact_snapshot_json IS NOT NEW.fact_snapshot_json
  OR OLD.plan_hash IS NOT NEW.plan_hash
  OR OLD.fact_snapshot_hash IS NOT NEW.fact_snapshot_hash
  OR OLD.created_by IS NOT NEW.created_by
  OR OLD.created_at IS NOT NEW.created_at
BEGIN
    SELECT RAISE(ABORT, 'approved plan content is immutable');
END;

CREATE TRIGGER site_magic_checkpoints_immutable_update
BEFORE UPDATE ON site_magic_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'site_magic_checkpoints is immutable');
END;

CREATE TRIGGER site_magic_checkpoints_immutable_delete
BEFORE DELETE ON site_magic_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'site_magic_checkpoints are recoverable and immutable');
END;

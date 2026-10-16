-- Link each bounded revision to the build that applies it. The build request
-- remains provider-neutral; this table preserves the product-level trace.
CREATE TABLE site_magic_revision_builds (
    revision_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (revision_id) REFERENCES site_magic_revisions(revision_id) ON DELETE RESTRICT,
    FOREIGN KEY (build_id) REFERENCES site_magic_build_requests(build_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_site_magic_revision_builds_tenant_time
    ON site_magic_revision_builds(tenant_id, created_at DESC);

CREATE TRIGGER site_magic_revision_builds_immutable_update
BEFORE UPDATE ON site_magic_revision_builds
BEGIN
    SELECT RAISE(ABORT, 'site_magic_revision_builds is immutable');
END;

CREATE TRIGGER site_magic_revision_builds_immutable_delete
BEFORE DELETE ON site_magic_revision_builds
BEGIN
    SELECT RAISE(ABORT, 'site_magic_revision_builds is immutable');
END;

CREATE TABLE site_magic_jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('intake', 'url', 'repository')),
    source_payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'queued', 'ingesting', 'directing', 'building', 'evaluating',
        'remediating', 'final_review', 'ready_for_review', 'published',
        'failed', 'quarantined'
    )),
    remediation_rounds INTEGER NOT NULL DEFAULT 0 CHECK (remediation_rounds BETWEEN 0 AND 2),
    rebuild_count INTEGER NOT NULL DEFAULT 0 CHECK (rebuild_count BETWEEN 0 AND 1),
    quality_summary_json TEXT,
    final_build_id TEXT,
    failure_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_site_magic_jobs_tenant_created
    ON site_magic_jobs(tenant_id, created_at DESC);

CREATE TABLE site_magic_builds (
    build_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    artifact_manifest_json TEXT NOT NULL,
    preview_locator TEXT NOT NULL,
    published_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES site_magic_jobs(job_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    UNIQUE (job_id)
);

CREATE INDEX idx_site_magic_builds_tenant_created
    ON site_magic_builds(tenant_id, created_at DESC);

CREATE TABLE site_magic_active_builds (
    tenant_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL,
    activated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (build_id) REFERENCES site_magic_builds(build_id) ON DELETE RESTRICT
);

ALTER TABLE public.site_magic_build_requests
    ADD COLUMN correlation_id TEXT NOT NULL DEFAULT '';

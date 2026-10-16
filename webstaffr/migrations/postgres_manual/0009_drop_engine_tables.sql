-- 0009_drop_engine_tables.sql
-- Postgres backend only, DORMANT -- do NOT apply at WebStaffr 4.0 cutover.
--
-- workflow_definitions and execution_records belonged to the workflow
-- engine (webstaffr/workflow.py, execution.py, executor.py, repository.py
-- in the prior repo) that WebStaffr 4.0 does not carry forward -- nothing
-- in this repo's application code reads or writes either table anymore.
-- They remain in the live Supabase project from the old app's migrations,
-- RLS-protected since 0004, posing no security gap by sitting unused.
--
-- Apply this only after WebStaffr 4.0 has run in production for at least
-- a week with no regressions, and only with explicit founder approval
-- (CLAUDE.md's Self-Approval Scope: DB schema changes against a live
-- production system are never self-approved). There is no rollback for a
-- DROP TABLE -- if there's any doubt these tables are truly unused,
-- don't run this.

DROP TABLE IF EXISTS execution_records;
DROP TABLE IF EXISTS workflow_definitions;

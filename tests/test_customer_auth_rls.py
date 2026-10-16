from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "webstaffr"
    / "migrations"
    / "postgres_manual"
    / "0017_customer_auth_rls.sql"
)


def _sql() -> str:
    return " ".join(MIGRATION.read_text().lower().split())


def test_customer_auth_rls_is_enabled_and_anon_is_revoked():
    sql = _sql()
    assert "alter table public.customer_users enable row level security" in sql
    assert "alter table public.tenant_memberships enable row level security" in sql
    assert "revoke all on table public.customer_users from anon, authenticated" in sql
    assert "revoke all on table public.tenant_memberships from anon, authenticated" in sql


def test_authenticated_users_can_select_only_their_own_rows():
    sql = _sql()
    assert "grant select on table public.customer_users to authenticated" in sql
    assert "grant select on table public.tenant_memberships to authenticated" in sql
    assert sql.count("to authenticated using ((select auth.uid()) = user_id)") == 2


def test_customer_data_api_has_no_mutation_grants_or_policies():
    sql = _sql()
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "for insert" not in sql
    assert "for update" not in sql
    assert "for delete" not in sql
    assert "security definer" not in sql

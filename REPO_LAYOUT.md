# Site Magic repository layout

`keithtortorich/site-magic` is the canonical home for Site Magic code.

| Area | Location |
| --- | --- |
| Python runtime and control plane | `webstaffr/site_magic*.py`, `webstaffr/site_magic_engine.py` |
| TypeScript generation and worker | `webstaffr/site_maker_engine.ts`, `webstaffr/site_magic_*.ts` |
| Shared renderer and schema dependencies | `webstaffr/site_renderer.py`, `webstaffr/site_schema.py`, `webstaffr/site_render_router.py` |
| Operator UI and customer templates | `webstaffr/templates/` |
| Database migrations | `webstaffr/migrations/` |
| Python tests | `tests/` |
| TypeScript tests | `tests_node/` |
| Architecture and governance | `docs/` |
| HVAC corpus and validation | `schemas/`, `scripts/`, `tests/test_validate_corpus.py` |

The source was migrated from the former NetBuild.Pro checkout as a coherent
bundle because the Site Magic modules import shared renderer, intake, database,
tenant, and authentication modules. The old checkout remains untouched for
rollback and comparison; future implementation changes belong in this repo.

Do not copy credentials, `.env` files, dependency caches, generated artifacts,
or unrelated application secrets into this repository.

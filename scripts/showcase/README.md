# Showcase journeys

## M0 local run

Start Postgres and Valkey and a local Ollama service. Use the project Python
environment, an existing fixture tenant with a knowledge base, its credential
in `SHOWCASE_FIXTURE_KEY`, and the owner connection in `MIGRATION_DATABASE_URL`.
Set `DATABASE_URL` to the application role connection and configure a local
Ollama chat model. Never print credentials or put them in evidence.
Set `DEPLOY_SHAPE=multi_tenant`: the reference company has more than one tenant in the database.

From the repository root, use the fixture tenant's slug:

```bash
scripts/showcase/setup_personas.sh --tenant "$TENANT_SLUG"
scripts/showcase/m0.sh
```

M0 uses `poetry` on PATH by default. Set `SHOWCASE_PYTHON` to the project Python
executable to override it; if neither runner is available, the script explains how to proceed.

Setup needs an existing tenant slug and the owner DSN in `MIGRATION_DATABASE_URL`.
It finds each principal by name, reuses valid saved keys, and otherwise issues a replacement
and revokes only the issued prefix recorded in its manifest. Other active keys remain
untouched; a `WARN` line reports their count and prefixes. If the manifest is lost,
setup issues fresh keys without revoking any existing keys. `--replace <persona>` forces rotation.
Optional `--tenant-id` and `SHOWCASE_FIXTURE_KEY` provide additional tenant verification.
Private state binds subsequent runs to the manifest tenant. No tenant is created.

M0 reads the default `.showcase` state directory and requires `SHOWCASE_FIXTURE_KEY`
to verify the manifest tenant. If state is incomplete, rerun setup for that same tenant.

M0 prints fixed failure reasons and exception class names only. Its complete server stderr stays
in `.showcase/m0-server.log`, created exclusively with mode 0600 under the private state directory.
Inspect it locally when startup fails; keep it out of shared output and evidence. Before rerunning,
move the previous log to a private archive outside the worktree. An existing log or symlink is refused.

Fixture and persona checks use public owner-role identity functions. The auditor reads deny and
`module_disabled` decisions through `GET /v1/decisions?request_id=...` in the Gateway edition.
Policy baseline and deny publication chain expected versions; a concurrent head change fails the
journey and rolls back its publications. Restore still appends only if its own deny version is current.

Choose an edition with `ENABLED_MODULES` when starting the API and worker. The default `all` enables every module. Gateway is always required.

| Journey | Edition modules | Completes at milestone tag | Scope |
|---|---|---|---|
| `m0` | `all` | `v0.15.0` | Platform foundations and lifecycle |
| `mg` | `gateway` | `v0.20.0` | Gateway product |
| `md` | `gateway,data,lineage` | `v0.26.0` | Data on the client's stack |
| `ma` | `gateway,agents` | `v0.29.0` | Agents and insights |
| `me` | `all` | `v1.0.0` | Enterprise readiness |

For example, start the Gateway edition with:

```bash
ENABLED_MODULES=gateway poetry run uvicorn api.main:app
```

The Data edition uses `ENABLED_MODULES=gateway,data,lineage`. The Agents edition uses `ENABLED_MODULES=gateway,agents`. The Assurance edition uses `ENABLED_MODULES=gateway,evidence`. Full uses `ENABLED_MODULES=all`. The sprint map records the milestones and completion scope.

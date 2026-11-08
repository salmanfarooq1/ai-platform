# Showcase journeys

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

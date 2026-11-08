# ADR-0013: Module boundaries and editions

**Status:** Accepted

## Context

The platform is one Python application with modules that can be enabled by edition. The module registry must describe optional code without importing it. Providers and cross-module work need typed contracts. A deployment also needs an explicit tenant shape.

## Decision

`core/modules.py` lists each module, its pillar, navigation group, and optional router, transport, or job-handler factory. `ENABLED_MODULES` accepts `all` or a comma-separated list. `gateway` is always required. Unknown names fail settings validation. The supported editions are Gateway (`gateway`), Assurance (`gateway,evidence`), Agents (`gateway,agents`), Data (`gateway,data,lineage`), and Full (`all`). `DEPLOY_SHAPE` is `single_tenant` by default or `multi_tenant`. Single-tenant startup rejects a database with multiple tenants, and tenant creation is serialized and limited to one. Both shapes keep tenant checks and row-level security.

The `module` stage runs after `principal`. It checks the action's registered module and trusted route-module attribution. A disabled capability is denied as `module_disabled`. Module composition roots load optional routes, transports, and job handlers only when enabled. The gateway package API is available to every module. `ports/` contains provider and cross-module contracts; `core/` does not import module implementations. `evidence/` and `gateway/` do not import each other, `api/`, or `workers/`. Agent, MCP, and sandbox code use the gateway package API and do not import gateway internals or evidence. Import-linter enforces these boundaries.

The gateway supports the current embedded mode, where the API and workers run the application code. Sidecar and standalone proxy modes are target deployment modes for Sprint 016; they are not implemented by this decision.

## Consequences

Editions can omit optional routes and jobs while keeping the gateway and decision evidence available. New modules must register metadata and action ownership, use ports at boundaries, and add edition coverage. `DataAccess` and `LineageEmitter` have typed contracts, but their real implementations arrive in later sprints. Tenant isolation remains required in every deploy shape.

## Alternatives considered

- **Import all module implementations at startup:** rejected because disabled modules would still load and module boundaries would be harder to enforce.
- **Allow modules to call one another directly:** rejected because cross-module behavior needs stable, typed contracts.
- **Treat tenant shape as a module setting:** rejected because tenant count controls startup and tenant creation across all modules.

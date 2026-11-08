# Information architecture

The application navigation is defined in `ui/src/app/nav.ts`. Its groups and owners are:

| Group | Pages | Owning module |
|---|---|---|
| Start | Overview, Walkthrough | Platform |
| Workspace | Ask | Agents |
| Workspace | Library, History | Gateway foundation |
| Governance | Requests, Decisions, Policies, Keys, Usage | Gateway |
| Governance | Agent runs | Agents |
| Platform | Modules, Trust, System | Platform and Gateway |

The Ask page uses Agent availability metadata before showing or submitting its Agent controls. The Modules page reads the module list. Trust and receipt verification remain available with the Gateway edition. Data and Lineage do not yet add navigation pages.

Navigation that depends on an optional module stays hidden until the signed-in session's module metadata is loaded. It also stays hidden when that module is disabled. The sidebar and command palette use the same filtered navigation. A session change clears the old module metadata. Ask controls and direct Agent run pages apply the same unknown and disabled checks.

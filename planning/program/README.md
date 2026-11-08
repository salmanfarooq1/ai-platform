# Program 2: governed data and agent platform

This folder is the master plan for sprints 011 to 032. The Architect wrote it on 2026-10-08 after researching the 2026–2027 landscape and reviewing an earlier GCP data portal. It was condensed from 36 sprints to 22 on 2026-10-11, after the owner set a new direction and a five-direction review.

The goal is one governed platform with three pillars:
- **Gateway:** security, governing every call.
- **Data:** connecting to and governing client data.
- **Agents:** running and monitoring our agents, the client's agents and external agents.

Every call leaves verifiable evidence. The platform is integration first: it connects to the client's existing systems instead of replacing them.

## Read order
1. [vision-and-architecture.md](vision-and-architecture.md): what we build, the pillars, modules and editions, deployment modes, the rules.
2. [stack.md](stack.md): every component with its pinned version, licence and memory cost.
3. [sprint-map.md](sprint-map.md): the 22 sprints, milestones, sellable and freeze points, order, and the old-to-new table.
4. [sprint-template.md](sprint-template.md): the five files in every pack, and the test pattern.
5. [branching-and-commits.md](branching-and-commits.md): branches, commit blocks, tags and merge rules.
6. [conventions.md](conventions.md): the one list of script names, scopes, action kinds and routes.
7. [reference-data-portal.md](reference-data-portal.md): what we take from the earlier portal, and what we avoid.
8. [review.md](review.md): the six-perspective review, the owner review, the coherence audit and the five-direction review.
9. [ui-delivery.md](ui-delivery.md): applicable UI and browser acceptance in each sprint.
10. [builder-method.md](builder-method.md): how the Architect and the Luna builders work: readiness gate, test spec, work packages, briefs and review.
11. The packs in `planning/sprints/011-*` to `032-*`. The old 36 packs are in `planning/sprints/_draft-36/`.

## Hard constraints for the whole program
- **Open source code and stack.** Everything we ship or run by default uses OSI-approved licences. No source-available licences (BSL, ELv2, SSPL, RSAL, Collate CL), and no proprietary runtime. Hosted model endpoints and managed cloud services are adapters the client chooses. They are allowed, but never required.
- **Runs anywhere, from one command.** Local Compose is the development and showcase vehicle. Real deployments run on cloud with one OpenTofu module per cloud and the same core (from 015). POCs start and stop on demand.
- **Integration first.** Clients connect their sources, warehouses, streams and agents through existing connectors. We do not write connectors where an open-source one exists.
- **The existing rules hold.** The 15 strict rules in `docs/architecture.md` section 2 and the working agreements in `AGENTS.md` apply to every sprint.
- **No commits by a model.** Every sprint ends with proposed commit blocks in `report.md`. A human runs them.

## Status
- Research, plan and six-perspective review: done (2026-10-08). Owner review and coherence audit: done (2026-10-09).
- Five-direction review and condensing to 22 sprints: done (2026-10-11).
- Packs:
  - 011 and 012 have the full five files.
  - 013 to 032 have `requirements.md`. Their full packs are written when each becomes next.
- Nothing is built yet. This branch (`planning/sprint-plans`) merges into `main` before Sprint 011 starts.

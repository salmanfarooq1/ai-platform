# Sprint 011: Independent QA review

Date: 2026-10-24. Read-only review of the working tree against `acceptance.md`. This review is independent of the Codex Architect review in `qa-review.md`.

## Verdict
Not ready to land. One bounded fix round is needed (`fix-brief.md`). No test was weakened. T11 (cache tenant index), the NumPy artifact binding, loopback ports and registry digests all hold.

## Re-run here
- 879 unit tests pass. 5 fail only because the Docker CLI was absent (`test_compose.py`).
- Ruff passes. Mypy passes on 147 files.
- The integration tier was not re-run, because Docker was down.

## Must fix
| # | Finding | Where | Acceptance |
|---|---|---|---|
| F1 | A change only under `ui/` sets backend=false, so the unit tests are skipped. That includes the UI proxy credential guard. A docs-only change skips the doc-link tests. Rename detection can hide a moved source file. | `scripts/ci/change_scope.py:14-17`, `.github/workflows/tests.yml` | A1, T6 |
| F2 | `PSF-2.0` is in the OSI allowlist, but SPDX marks it not OSI-approved. | `scripts/supply_chain/osi-licences.txt:9` | A4, T2 |
| F3 | `ui/Dockerfile.ui` uses `node:22-alpine` and `nginx:alpine` with no digest. The image is never scanned. | `ui/Dockerfile.ui:2,9`, `check_pins.py` | A7, T1, T7 |
| F4 | The new `pgdata_trixie` volume leaves existing data behind without warning. The upgrade docs give no commands. | `docker-compose.yml:11`, `docs/*-upgrade.md` | data safety |
| F5 | Forked Kafka, SeaweedFS and Ollama builds have to be maintained by us. The Kafka build downloads exact Alpine packages that will 404. The Ollama rebuild was never tested on a real model pull or embedding. | `docker/kafka`, `docker/seaweedfs`, `docker/ollama` | B3, B4, B5 |

## Owner decisions (2026-10-24)
- **D1:** use the upstream images for the optional profiles (`streams`, `lake`, `models`), pinned by digest. Known criticals in those images go in an exception file with the CVE, image, profile, reason and an expiry date of at most 30 days. An expired exception fails. A critical finding in the default stack (app, worker, Postgres, Valkey) has no exception.
- **D2:** accept `PSF-2.0` as a reviewed exception for `aiohappyeyeballs` 2.6.1 only. It comes out of the OSI allowlist.

## Low (fixed in the same round)
- `scripts/setup_db.sh:13` hard-codes `postgres:postgres`.
- Stale "up postgres redis" text: `setup_db.sh:4`, `verify/observability.sh:4`, `verify/openshell.sh:7`. ADR-0008 still names Redpanda.
- MCP no longer logs unexpected errors at all. Log the exception type and tool name, without the message.
- `test_config_mode.py:55-63` leaks `LOG_LEVEL` into `os.environ`.
- Kafka `AUTO_CREATE_TOPICS_ENABLE=true`.
- Preflight checks only fixed ports, not the ports of the selected profiles.
- `npm exec --yes` runs licence-checker and cyclonedx-npm without a version pin.

## Deferred
- The rerank extras (torch, nvidia) are outside the licence gate. This belongs to 013.
- B2's "34 live cases" includes fake and mocked cases. Report the real split.

## Landing
Commit the evidence named in the docs (153 files, 2.6 MB), not all 407. The full set stays in `/home/ubuntu/ai-platform-snapshots/011-accepted-v3`. Add `.env.example` to the ops block. Leave the 012 planning files out of the 011 commits.

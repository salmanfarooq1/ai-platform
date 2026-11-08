# Image remediation status

Prometheus has a verified security replacement; no advisory is ignored. Postgres stays on 16, existing volume data is preserved, and part b remains gated.

## Accepted Prometheus security fix

`prom/prometheus:v3.15.1@sha256:fa3302279710be2f21a8301ec17a8b4f2301fd829bd113839b3b6b02b6f191a2` is published October 21. The [tagged maintainer changelog](https://raw.githubusercontent.com/prometheus/prometheus/v3.15.1/CHANGELOG.md) confirms that release date and fixes through Go 1.27.3 and x/net 0.60.0. The security-age exception is recorded in pins. The exact distributed licence is Apache-2.0, the scan reports no vulnerabilities, the current config validates, and the candidate replays/queries samples written by 3.14.0 in a dedicated test volume. This is a bounded WAL compatibility smoke check; existing volumes were not mounted or changed.

[Registry metadata](evidence/rework-image-registry-refresh.json), [release](evidence/rework-prometheus-release.txt), [version/config](evidence/rework-prometheus-new-artifact.txt), [licence](evidence/rework-prometheus-new-licence.txt), [scan](evidence/rework-prometheus-new-candidate.txt), [data compatibility](evidence/rework-prometheus-data-compat.txt), [36 existing tests](evidence/rework-prometheus-pin-tests.txt), [Compose](evidence/rework-prometheus-compose.txt). The compose pin is updated; the optional profile, ports and volume names are unchanged.

## Rejected Grafana candidate

The registry reports Grafana 13.2.4 at `sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f`, published October 13. Its [maintainer release](https://github.com/grafana/grafana/releases/tag/v13.2.4) lists security fixes. [Registry evidence](evidence/rework-image-candidates.txt) and the [completed candidate scan](evidence/rework-grafana-candidate-scan.txt) preserve the exact artifact.

The scan still rejects fixed-critical GO-2026-6612 findings in embedded Go toolchains and `golang.org/x/net`. The [Go advisory](https://pkg.go.dev/vuln/GO-2026-6612) identifies fixed Go 1.26.9/1.27.2 and x/net 0.60.0. Upgrading only the container's operating-system packages cannot repair those compiled components. The candidate is not substituted into compose, and its recent publication does not justify accepting its findings.

## Remaining compatible artifact work

- **pgvector/Postgres 16:** the registry still serves the existing 0.8.7-pg16 digest. A child rebuild would need the exact pinned base, signed Debian security packages fixed for every recorded critical finding, pinned package versions/repository inputs, a recorded final manifest digest, and the database contracts and migration checks on Postgres 16. No data-volume recreation or major-version upgrade is allowed. A local rebuild also needs a concrete CI-service consumption path; an unpublished local tag is not a verified registry digest.
- **Grafana:** require maintainer images or reproducible builds with every affected embedded Go component rebuilt against fixed toolchains/modules. Verify the full resulting image, including plugins; a newer application version alone is insufficient. No fixed compatible image has yet been established by this pass.
- **Redpanda:** the pinned 24.2 artifact fails the earlier scan. The [maintainer lifecycle page](https://docs.redpanda.com/streaming/current/get-started/release-notes/) marks 24.2 end of life. A jump to 26.x cannot be assumed compatible with existing data or CLI operations. Require a verified compatible rebuild or a separately specified upgrade path and its tests. The planned Apache Kafka replacement remains part b and does not close part-a acceptance.
- **Ollama:** the host attempt timed out, then the same scanner/database completed inside Docker with exit 2. Fixed-critical x/net, x/crypto and Go stdlib findings remain. The newest 0.40.7 tagged source still declares x/crypto 0.43.0 and x/net 0.46.0, so a fixed artifact has not been established by its newer version number. [Captured declarations](evidence/rework-ollama-new-source.txt). A compatible replacement must rebuild those components and pass the same gate; no finding is accepted. [Full scan and exit](evidence/rework-ollama-local-complete.txt).

These are artifact requirements, not assertions that an unbuilt replacement is compliant. Candidate digests, package versions, licences or clean scans will only be recorded as accepted after verification. The current independent runner captures the existing image failures separately from licence and SBOM results.

## Application security refresh

The fresh scan rejects certifi 2026.6.17 for [GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2). The selected 2026.10.19 pin meets the scanner fix floor and the maintainer's earlier patched-version floor. Its October 20 publication uses the security exception; the exact wheel hash and MPL-2.0 licence are [verified](evidence/rework-certifi-wheel.txt). [Lock comparison](evidence/rework-certifi-lock-diff.txt) confirms no other package changed. The rebuilt application passes the same critical threshold: [completed build/scan](evidence/rework-certifi-image.txt). All seven final images now have completed individual results in the [captured aggregate](evidence/rework-final-image-results.txt). The full independent runner returned failure; its original timeout is retained separately from the completed Ollama retry.

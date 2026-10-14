# Sprint 011: Threat model
## Assets
- The CI pipeline and its tokens (`GITHUB_TOKEN`).
- The dependency tree (Python, npm, images).
- Secrets in the repo history and in local env files.

## Trust boundaries crossed
- Package registries (PyPI, npm) and image registries into CI and the local machine.
- A local `.env.local` into the process environment.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A dependency or image is swapped upstream under the same tag. | Tampering | Hash-locked exports, images by digest. | `export_locks.sh` drift check in CI; pins grep in `evidence/pins.txt`. |
| T2 | A non-OSI or source-available package enters the default stack. | Tampering (licence) | Licence gate with an OSI allowlist. | `test_licence_gate.py` (BUSL fixture fails). |
| T3 | A secret is committed. | Information disclosure | gitleaks CLI over the full history with `--redact`. | `secret-scan` job; `evidence/gitleaks.txt`. |
| T4 | A local `.env.local` silently overrides a real environment value (for example a hosted `MODE`). | Tampering | `override=False`. | `test_real_env_beats_env_local`. |
| T5 | A new skip hides a broken service in CI. | Repudiation | Skip allowlist file with a reason per entry and an exact count. | `test_check_skips.py`. |
| T6 | A known critical CVE ships in an image. | Elevation of privilege | Image scan in CI with a reasoned ignore file. | `evidence/image-scan.txt`. |
| T7 | Tools send telemetry from CI. | Information disclosure | `DEEPEVAL_TELEMETRY_OPT_OUT`, `DO_NOT_TRACK=1` at workflow level. | A unit test reads both workflows and checks the env keys. |

## Abuse cases
- A pull request edits `licence-exceptions.txt` to let a BUSL package in. The exceptions file needs a reason per line, and review sees it in the diff.
- A pull request adds a skip to the allowlist to hide a failing service. The entry needs a `count` and a written `why`, and the change shows in review.

## OWASP items in scope
- ASI04 (agentic supply chain): dependency, image and licence controls.
- LLM03 2026 (supply chain): the same controls. Model weights are covered in Sprint 014.
- Other ASI items: none. No agent behaviour changes.

## Residual risks
- The gate trusts package metadata. A package that lies about its licence passes.
- Path filters can skip a job when a change touches an unlisted path. The filters list backend roots on purpose.

# Sprint 040: Blueprint

## Receipt v2 format
- COSE_Sign1 (RFC 9052), tagged. Protected header: `alg` -8 (EdDSA), `kid` (the key id bytes), content type `application/json`, CWT claims (label 15) with `iss` (`RECEIPT_ISSUER`) and `sub` (the decision id). This is the SCITT signed-statement shape.
- Payload: the canonical JSON of `{chain, decision}`, where `decision` is the record v2 with its extensions in the evidence core's fixed order. The same bytes the chain hashes.
- `key_id` stays the first 16 hex characters of the SHA-256 of the raw public key, so v1 and v2 name keys the same way.

## Contract
- `GET /v1/receipts/{decision_id}`: JSON `{format: "cose-v2", cose: <base64>, decision, chain, attestation}` by default. `Accept: application/cose` returns the raw bytes. `?format=v1` returns the Sprint 008 Ed25519 receipt.
- `POST /v1/receipts/verify` accepts both formats and reports which.
- `GET /v1/receipts/keys` gains `role` (receipt, log, tsa), `status` (active, previous, revoked) and `revoked_at`.
- The policy input for replay: reuse Sprint 031's `GET /v1/decisions/{id}/policy-input` (`audit:read`; the stored input document, hashes only) and the bundle tar stored by `bundle_sha256` in `policy_bundles` (Sprint 031). The server-side replay stays Sprint 032's `POST /v1/decisions/{id}/replay`. The offline `replay` subcommand below gives the same answer as that route and as `scripts/verify/replay_decision.py` (031, `--explain` from 032). No new route.
- OpenAPI snapshot refreshed.

## Ports and adapters
- `ports/signer.py`: `Signer` with `key_id`, `public_key_raw()`, `sign(data: bytes) -> bytes`. Frozen info dataclasses.
- `adapters/file_signer.py`: Ed25519 from a mounted file. `adapters/pkcs11_signer.py`: `python-pkcs11` against a token and label. The library is imported only there.
- Registry: one signer per role, from `RECEIPT_SIGNER`, `LOG_SIGNER`, `TSA_SIGNER` (`file` or `pkcs11`).
- Settings in `core/settings.py`: `RECEIPT_SIGNING_KEY_FILE`, `LOG_CHECKPOINT_KEY_FILE`, `TSA_SIGNING_KEY_FILE`, `PKCS11_MODULE`, `PKCS11_TOKEN_LABEL`, `PKCS11_PIN_FILE`, `RECEIPT_KEY_REVOCATIONS_FILE`. Startup refuses two roles with the same public key. `RECEIPT_SIGNING_KEY` (env) still works; setting it and the file together is refused.
- Contract suite `tests/contracts/test_signer_contract.py` on both adapters.

## Revocation
`RECEIPT_KEY_REVOCATIONS_FILE`: a JSON list of `{key_id, revoked_at, reason}`. A receipt whose record `created_at` is at or after `revoked_at` for its `kid` fails. Earlier receipts keep verifying. Purge checkpoints follow the same rule.

## Attestation (record v2 extension `attestation`)
`{sandbox_image_digest, model_digest, policy_bundle_hash, tee: null}`. Filled from the run spec (Sprint 009), `models.lock` (Sprint 014) and the policy bundle (Sprint 031). Unknown stays null.

## Offline verifier v2
`scripts/verify/receipt.py` stays standalone: standard library, `cryptography`, `cbor2`. New: `receipt` reads both formats; `--keys` includes revocations; `--require-v2` fails a v1 receipt; `replay --receipt R --bundle B.tar.gz --input I.json` checks both hashes, runs `opa eval` (binary on `PATH`, or `--opa-docker`), and compares allow, deny or approval required with the record.

## Data
No migration expected (receipts are built on read; revocations are a file). If one is needed: the next free number after Sprint 039's head.

## UI (follow `.claude/skills/governed-design/SKILL.md`)
Evidence > Receipts: lookup, format badge, `kid` and key status, attestation fields, verify result per check. Keys list with roles and revocations.

## Compose and scripts
- A key rotation section in `docs/operations.md`: rotate, list the old key as previous, revoke, verify. `scripts/verify/key_drill.sh` runs the drill on a throwaway database.
- CI installs `softhsm2` for the PKCS#11 contract case.

## Tests
- Unit: COSE encode and decode; header fields; v1 and v2 both verify; a v1 receipt under `--require-v2` fails.
- Integration: rotation drill; revocation cut; replay match and mismatch; attestation fields set.
- Verifier parity test: server and offline verifier agree on every sample.
- Playwright: verify a v2 receipt and a tampered one.

## Docs
ADR-0029 (receipts v2: COSE, SCITT shape, key management). Append to ADR-0012. `docs/operations.md` (the rotation and revocation runbook), `docs/configuration.md`.

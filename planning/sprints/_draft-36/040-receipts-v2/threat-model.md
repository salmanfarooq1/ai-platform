# Sprint 040: Threat model

## Assets
- The receipt, log and TSA signing keys. The revocation list.
- Receipts as evidence held by third parties.
- The policy input documents used for replay.

## Trust boundaries crossed
- Mounted key files and the PKCS#11 token to the API and worker.
- Receipts leaving the platform to auditors and the offline verifier.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Forged receipt | Spoofing | EdDSA over the canonical payload; `kid` must be known | `test_forged_cose_receipt_fails` |
| T2 | Header swapped (other `kid`, `alg`) | Tampering | Protected header is signed; `alg` fixed to EdDSA | `test_cose_header_tamper_fails` |
| T3 | Downgrade: attacker offers a v1 receipt to avoid v2 checks | Tampering | `--require-v2` in the verifier; v1 only on explicit request | `test_require_v2_rejects_v1` |
| T4 | Stolen key keeps signing after the theft | Spoofing | Dated revocation; receipts after `revoked_at` fail | `test_revoked_key_after_time_fails` |
| T5 | One key compromise breaks receipts, log and TSA together | Elevation | Separate keys per role; startup refuses a shared key | `test_same_key_two_roles_refused` |
| T6 | Key printed in logs or errors | Info disclosure | Only `key_id` is logged; file contents never echoed | `test_signing_keys_not_logged` |
| T7 | Replay uses a different bundle and "proves" an allow | Tampering | Bundle and input hashes checked against the record before eval | `test_replay_bundle_hash_mismatch` |
| T8 | Replay input leaks content | Info disclosure | Input documents hold ids, scopes, purpose and hashes only | `test_policy_input_has_no_content` |
| T9 | Old receipts stop verifying after rotation | DoS | Previous keys stay listed | `test_rotation_keeps_old_receipts` |
| T10 | Revocation list edited to un-revoke a key | Tampering | The list is deployment config, reviewed in change control; the drill shows its effect | documented residual risk |

## Abuse cases
- An insider with database owner rights rewrites a chain. Issued receipts still fail against it (ADR-0012). External anchoring comes in Sprint 041.

## OWASP items in scope
- LLM Top 10 and ASI: none directly. This sprint protects evidence, not model or agent behaviour. ASI10 (rogue agents) is helped indirectly: actions stay provable.

## Residual risks
- The revocation list is a file with no signature of its own. Sprint 041's log can carry it.
- Revocation is by record time from the database clock. A host with a wrong clock weakens it until the Sprint 041 clock pre-flight.

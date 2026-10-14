# Sprint 038: Threat model

## Assets
- Personal data in prompts and answers (CRM contacts, HR records).
- Guard verdicts as evidence. The labelled set and thresholds.
- The guard model weights and the spaCy model.

## Trust boundaries crossed
- Gateway to the `guard` service and to Ollama (compose network).
- Untrusted text (user input, documents, tool results) into the detectors.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Evasion by encoding (spacing, homoglyphs, base64) | Tampering | Text normalised before both detectors; evasion samples in the labelled set | `test_guard_evasion_samples` |
| T2 | Guard service down or slow, call goes through | Elevation | Fail closed with `guardrail_unavailable` | `test_guard_down_denies`, `test_guard_budget_overrun_denies` |
| T3 | Swapped guard weights | Tampering (ASI04) | Digest checked against `models.lock` at startup and in the record | `test_guard_digest_mismatch_refuses_start` |
| T4 | PII copied into the record or logs | Info disclosure (LLM02) | Extension holds counts only; a test scans records and logs | `test_guard_extension_has_no_text` |
| T5 | Masked output leaks through a second channel (tool arguments) | Info disclosure | `output.check` on agent text and tool arguments that leave the run | `test_tool_arguments_masked` |
| T6 | Breaker rules edited out of policy | Elevation | Breaker rows in the decision-table suite; bundle hash in records | `test_breaker_rows_both_engines` |
| T7 | Guard prompt injection makes the guard say "safe" | Tampering (LLM01) | The guard sees the text as data in a fixed template; injection samples in the set | `test_guard_injection_samples` |
| T8 | False positives block normal work | DoS | Precision threshold and a per-tenant `block_above` | `test_precision_threshold_gate` |
| T9 | Runtime model download | Tampering | Network blocked in the test; models baked or pre-pulled | `test_guard_no_runtime_download` |

## Abuse cases
- An attacker probes the guard to learn its threshold. Each denied call is recorded and counts against the rate limit.

## OWASP items in scope
- LLM01 Prompt injection: T1, T7.
- LLM02 Sensitive information disclosure: T4, T5.
- LLM05 Improper output handling: output stages.
- ASI04 Supply chain: T3, T9.
- ASI02 Tool misuse: T6.

## Residual risks
- No detector is complete. Recall below 1.0 means some PII or injections pass. The numbers are recorded per run.
- Model drift on a new digest: the eval reruns when `models.lock` changes.

# Sprint 023: Threat model

## Assets
- Grants: they decide who reads which columns and rows.
- The approval chain and its records.
- Extract files and their download URLs.
- Listing metadata visible across tenants.

## Trust boundaries crossed
- A consumer tenant creates a request on a producer tenant's product.
- An approver's decision becomes a grant through a worker.
- A presigned URL hands a file to a client outside the API.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Requester approves their own request (or owner, or certifier) | Elevation of privilege | `duties` stage with server-built facts | `test_duties_stage.py::test_requester_owner_certifier_denied` |
| T2 | Request changed after approval (more columns, later expiry) | Tampering | Approval quotes `request_hash`; worker re-checks it | `test_approval_races.py::test_changed_request_rejected` |
| T3 | Two approvers race on one step, or one approves twice | Tampering | Row lock; unique `(kind, subject_id, step)` on `approvals`; one step per principal | `test_approval_races.py::test_concurrent_approvals` |
| T4 | Grant inserted without a request | Elevation of privilege | `gap_app` has no INSERT on `grants`; the worker calls SECURITY DEFINER `grant_create(request_id)`, which checks every step | `test_grant_queue.py::test_no_grant_without_request` |
| T5 | Approver group changed after the request to add a friend | Tampering | Chain and policy version copied onto the request | `test_access_requests.py::test_chain_frozen_at_creation` |
| T6 | Expired or revoked grant still used | Elevation of privilege | `expires_at` and state checked on every use; version bump on revoke | `test_grant_expiry_revoke.py` |
| T7 | Extract URL shared or replayed | Information disclosure | Short TTL; objects deleted on revoke; each URL issue recorded | `test_extract_urls.py::test_url_expires`, `test_revoke_deletes_objects` |
| T8 | Consumer tenant reads producer data or other listings beyond metadata | Information disclosure | `listings_visible_to` returns metadata; RLS on requests and grants; extracts only of granted columns | `test_access_tenancy.py` |
| T9 | Row filter used as SQL injection | Elevation of privilege | Structured filter, ops allowlist, columns checked, values bound | `test_access_requests.py::test_row_filter_structured_only` |
| T10 | CSV extract carries formula injection | Tampering | Formula cells neutralised | `test_extract_urls.py::test_csv_formula_neutralised` |
| T11 | Approver denies having approved | Repudiation | Insert-only approval rows with decision ids | `test_access_requests.py::test_approval_recorded` |

## Abuse cases
- An analyst with `data:steward` requests access and approves it from the same key. Denied.
- An analyst edits the request columns after step one approves. Step two quotes the old hash and gets 409.

## OWASP items in scope
- OWASP Top 10:2025 A01 Broken Access Control (T1, T4, T6, T8), A05 Injection (T9, T10), A06 Insecure Design (TOCTOU, T2, T3).
- ASI03 Identity and Privilege Abuse: grants are the privilege an agent will later inherit from its user.
- LLM Top 10: none. No model is called.

## Residual risks
- A presigned URL works until its TTL ends, even after revocation, if the object was fetched in that window.
- Groups are local until SSO (035).

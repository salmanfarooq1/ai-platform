# Sprint 040: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 039's report. `check_skips.py` passes with the allowlist. Evidence: `checks.txt`
- [ ] **A2.** A v2 (COSE) receipt and a v1 (Ed25519) receipt both verify on the server and offline. A tampered payload, header or signature fails. Evidence: `receipts-v1-v2.txt`
- [ ] **A3.** The rotation drill passes: receipts signed before the rotation still verify, new receipts carry the new `kid`, and a receipt signed after a key's revocation time fails. Evidence: `key-drill.txt`
- [ ] **A4.** Startup refuses the same key for two roles. The PKCS#11 adapter passes the signer contract on SoftHSM. Evidence: `keys-separate.txt`, `pkcs11.txt`
- [ ] **A5.** `receipt.py replay` with the bundle and input reproduces the stored outcome, and reports a mismatch for a changed bundle. Evidence: `replay.txt`
- [ ] **A6.** A receipt for an agent model call shows the sandbox image digest, model digest and policy bundle hash, with `tee` empty (Playwright on Evidence > Receipts). Evidence: `attestation.txt`, `playwright.txt`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

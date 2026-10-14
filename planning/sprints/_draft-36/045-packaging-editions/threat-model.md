# Sprint 045: Threat model
## Assets
- Release wheels, images and their hashes.
- Backups, which hold all tenant data, the log and (stored apart) the signing keys.
- The edition boundary: what an install can reach.

## Trust boundaries crossed
- Build machine to `dist/` to an installing machine.
- Backup files leaving the running system and coming back on restore.
- Package index lookups during install.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A public package with the same name is installed instead of ours | Spoofing | Install with `--no-index --find-links dist` only; hashes checked against `SHA256SUMS` | `test_install_edition_uses_no_index`, `test_sha256sums_checked` |
| T2 | A wheel ships another module's code | Elevation of privilege | Wheel RECORD test; import-linter contracts | `test_wheel_contains_only_own_packages` |
| T3 | A disabled module's route stays open in an edition | Elevation of privilege | Registry answers `module_disabled`; smoke set checks it | `test_gateway_edition_data_routes_disabled` |
| T4 | A non-OSI component enters the default stack | Tampering (supply chain) | Licence report gate on release | `test_licence_report_fails_on_seeded_fixture` |
| T5 | A model or image differs from the SBOM | Tampering | Digests from `models.lock` and pins; check script | `test_sbom_model_digests_match_lock` |
| T6 | Restoring an old backup silently rolls back evidence | Repudiation | Restore drill checks log consistency against a checkpoint saved before the backup; runbook says to keep checkpoints apart | `test_restore_detects_rollback` (in `restore.sh`) |
| T7 | Keys leak through a backup archive | Information disclosure | Keys backed up apart from data; file modes `0600`; never in the data archive | `test_backup_archive_has_no_keys` |
| T8 | An edition compose file ships a default password | Spoofing | Compose check for required secrets; no defaults | `test_edition_compose_no_default_passwords` |

## Abuse cases
- An operator runs `pip install gap-dataplane` from a public index. The docs and scripts never do; the install script refuses without `dist/`.
- A restored copy is used to replay "why was this allowed" on old data. Receipts still verify; the log shows the restore point.

## OWASP items in scope
- ASI04 Agentic supply chain and LLM03 Supply chain: wheels, images and models are pinned, hashed and listed.
- ASI10 Rogue agents: none new; editions without M3 run no agents.

## Residual risks
- Wheels and SBOMs are hashed, not signed. Signing release artifacts is a program 3 item.
- Backups are not encrypted by the scripts. The runbook says to store them on encrypted media.
- The Full edition does not fit in the 12 GB WSL limit with every profile at once. Profiles are switched per task.

# LiteLLM check

Locked version: **1.103.2**, unchanged. [Wheel inspection](litellm-wheel.txt) verifies the Linux wheel SHA-256 against `poetry.lock` before reading its metadata and licence. Metadata: `License-Expression: MIT`. Licence-file SHA-256: `b170d6bf8e8835dd357e011681db028f4d51e2fb0ea892058f56e01fb39b8273`.

The [tagged repository licence](https://github.com/BerriAI/litellm/blob/v1.103.2/LICENSE) matches the wheel: core content is MIT; a separate licence applies to `enterprise/` if present. [Distribution and history inspection](litellm-history.txt) finds no enterprise directory in the installed distribution. No non-OSI core licence change was found in this check.

The project's [March incident notice](https://docs.litellm.ai/blog/security-update-march-2026), published March 24 with later updates, confirms compromised PyPI releases **1.82.7 and 1.82.8**. The project reports a clean 1.83.0 release through a rebuilt pipeline. The current lock uses neither affected version. All 17 lock-bearing revisions reachable from local refs were inspected; recorded versions are 1.89.2 and 1.103.2, with no affected revision. This checks local recorded locks; it does not establish the history of unrecorded installations or unreachable git objects.

Primary-source searches:
- `site.github.com/BerriAI/litellm security March 2026 PyPI`
- Project March 2026 security notice and its linked release updates.
- `BerriAI/litellm` at `v1.103.2`, `LICENSE`.
- Exact version's [PyPI metadata](https://pypi.org/pypi/litellm/1.103.2/json) and the lock-hash-verified wheel.

Result: the named incident does not affect any inspected lock; the installed core licence is MIT. No LiteLLM blocker and no version change. Python licence-gate blockage concerns NumPy, recorded separately.

# Licence remediation proposal

Status: the selected bounded source amendment is implemented and under final verification. The OSI-only policy is unchanged.

## NumPy exact-artifact correction

The reviewed artifact is only the CPython 3.11 Linux x86_64 wheel `numpy-2.4.2-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`, SHA256 `c02ef4401a506fb60b411467ad501e1429a3487abca4664871d9ae0b46c8ba32`. Its broad upstream expression and every original notice are retained. No version-wide exception is added.

The hash-verified source archive is SHA256 `659a6107e31a83c4e33f763942275fd278b21d095094044eb35569e86a21ddae`. The completed audit verifies all 8,242 original source files remain unmodified, builds every default target, records 229 compiler commands and the full transitive compiler-header dependencies, and inspects all 1,042 official wheel members plus the source-file symbols in its 21 NumPy libraries. Neither CC0 implementation is a compiled input or a distributed source member. The full captured commands/dependencies and exact upstream-wheel inventory are in [the audit directory](evidence/numpy-audit/); [summary](evidence/autonomous-numpy-audit.txt).

- `numpy/random/src/splitmix64` is used by standalone benchmark/test-data generators. The extension source lists in the [exact release build](https://github.com/numpy/numpy/blob/v2.4.2/numpy/random/meson.build) do not build those generators or splitmix64. The official random extension source-file symbols agree with those selected inputs.
- Highway's `hwy/contrib/random/random-inl.h` implements Xoshiro. It is used by Highway's own standalone random test, not by NumPy's [manually selected Highway build](https://github.com/numpy/numpy/blob/v2.4.2/numpy/_core/meson.build). NumPy selects `abort.cc` and the separate sort implementation; the completed transitive compiler dependencies contain no random-inl header. No Xoshiro/splitmix64 symbols or source members appear in the inspected official wheel.

This is an artifact-specific code-provenance determination using upstream source selection, completed compiler dependencies, and the exact publisher wheel's member and source-symbol inventory. It is not a claim that the locally built wheel is byte-identical to the publisher wheel. The PyPI integrity-provenance endpoint returned 503; no unavailable attestation is claimed as evidence. The local wheel is not installed or substituted.

The corrected effective expression also records the actually bundled OpenBLAS/LAPACK/GCC libraries, rather than dropping their terms:

`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND BSD-3-Clause-Open-MPI AND (GPL-3.0-or-later WITH GCC-exception-3.1) AND LGPL-2.1-or-later`.

The [SPDX primary licence data](https://github.com/spdx/license-list-data/blob/v3.28.0/json/licenses.json) marks the additional BSD Open-MPI, GPL and LGPL licences OSI-approved. The [GCC exception](https://spdx.org/licenses/GCC-exception-3.1.html) is an explicit additional permission; only this complete reviewed `WITH` expression is accepted. Unknown exceptions and non-approved base licences remain rejected.

The gate binds this determination to the exact wheel hash in `poetry.lock`, interpreter/platform, and all 1,041 immutable installed members. It rejects changed or extra code/binaries, missing notices, symlink files/directories/parents and bytecode that differs from the audited source. Original wheel RECORD is installer-mutated and is handled separately; original licence notices are immutable members. Other NumPy versions, Python ABIs and platforms fail closed pending their own artifact audit. Regression evidence: [artifact tests](evidence/autonomous-controls-final.txt).

Reproduce with `scripts/supply_chain/audit_numpy_artifact.py --help`; use the exact archive/wheel hashes above and the completed meson build directory. The captured compiler setup and build tools are retained with the audit evidence.

## Selected UI source boundary

Permit changes only to `ui/package.json`, its lock, `ui/src/styles/fonts.css`, the font assets and notices, and the landing animation loader/consumers named below. Associated existing tests and bundle checks remain binding. No product routes, layout, copy, design tokens or application-console behavior change.

1. Preserve the exact installed Geist Sans and Mono variable font bytes as self-hosted assets with their OFL notice. Their hashes and current consumers are in [artifact evidence](evidence/rework-ui-artifacts.txt). Remove the font wrapper dependency so its Next/caniuse-lite closure is no longer required. Confirm the resulting production closure rather than assuming that removal eliminates every CC-BY dependency.
2. Replace the direct GSAP dependency in `ui/src/landing/gsap-loader.ts`, `landing-page.tsx` and `scroll-story.tsx` with browser animation primitives, intersection observation and CSS sticky positioning. Preserve reveal timing, scroll-panel order, cleanup and resize behavior. Keep the existing reduced-motion and narrow-screen static branches. Preserve dynamic loading and the application bundle boundary.
3. Verify font hashes before/after, run all existing UI checks and all 82 browser cases without new skips, and compare desktop, narrow-screen and reduced-motion behavior. Run the reconciled production licence gate and regenerate the npm SBOM. No metadata exception can replace this migration.

The selected amendment is recorded in requirements, blueprint, brief and architect-disposition.md. Exact font hashes are preserved in evidence/autonomous-fonts.json. The production closure now contains 236 identities and passes the reconciled licence check; all 207 Vitest cases pass with bounded concurrency. Full browser verification remains required.

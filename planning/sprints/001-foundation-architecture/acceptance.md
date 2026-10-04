# Sprint 001: Acceptance

Evidence goes in `evidence/`.

- [x] **B1.** Every file path cited in `FOUNDATION.md` and the ADRs exists.
  - Check: extract each path with `grep -oE '`[a-z_/]+\.(py|sql|yaml|md)`'`, then `ls` it.
  - Evidence: `paths.txt`
- [x] **B2.** Rules 1–15 each appear in the §4 table with a sprint number.
  - Evidence: `rules-table.txt`
- [x] **B3.** ADRs 0001–0005 each have Status, Context, Decision, Consequences and Alternatives.
  - Check: `grep -c '^## ' docs/adr/000*.md` shows 4 per file, with Status on its own line.
  - Evidence: `adr-sections.txt`
- [x] **B4.** Sprint numbers agree across `ROADMAP.md` and `FOUNDATION.md` §4 and §5.
  - Evidence: a note in `report.md`
- [x] **B5.** No dates or durations, and no "demo" or old product name.
  - Check: `grep -rniE "verity|demo|[0-9]+ (day|week|month|hour)s?" docs/architecture docs/adr planning/ROADMAP.md` prints nothing.
  - Evidence: `grep-wording.txt`
- [x] **B6.** No code files are changed.
  - Check: `git diff --stat -- '*.py' '*.js' '*.jsx' '*.sql'` shows nothing from this sprint.
- [x] **B7.** `planning/STATE.md` and `CHANGELOG.md` are updated.

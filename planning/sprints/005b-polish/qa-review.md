# Sprint 005b: QA and code review

The QA agent returned this as text, and the Architect saved it.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass | 873 passed, 0 skipped |
| A2 | pass, with caveats | See M1 and L1 |
| A3 | pass | |
| A4 | Architect re-run | 70 Playwright passed (the Architect's run). QA read the specs only |
| A5 | Builder evidence | 0 axe violations |
| A6 | pass | Desktop 99, mobile 85 |
| A7 | pass | No GSAP or WebGL in `/app` chunks |
| A8 | pass, with caveats | See M2, M3 and L3 |
| A9–A13 | pass | |

## Findings
**High:** none.

**Medium**
- **M1:** a denied console read was hidden as "console only", so probing attempts never raised "blocked".
- **M2:** one landing line overclaimed: "Answers come from the documents the policy allows, and nothing else".
- **M3:** the claim map is self-declared, and the copy check only verifies item numbers.

**Low**
- **L1:** the reason catalogue scan reads string literals only.
- **L2:** the grouped queries aggregate the whole tenant history.
- **L3:** three wording issues: "receipt is issued", "prove", and "Nothing is allowed by default".
- **L4:** the `collection` key in localStorage isn't on the allowed list.
- **L5:** there's no hostile-input test for the command palette.
- **L6:** the color guard misses named colors and can flag a `#add` anchor.
- **L7:** the A4(c) count isn't asserted, and the URL regexes are loose.
- **L8:** the walkthrough treats any 404 as "no passage matched".

## Architect disposition
- **Builder:** M1, M2, L1 and L3–L8, each with a test where it's code.
- **Risk:** L2 is recorded as S5b-1 in RISKS. Retention in Sprint 008 bounds it.
- **M3:** the Architect signs off the final landing and how-it-works copy line by line against the may-claim list (see `report.md`). That is the review gate for copy, since no script can judge whether a claim is true.

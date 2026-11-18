# CLAUDE.md

Read `AGENTS.md` first. It holds the instructions every model follows.

After that, read `planning/MAP.md` (the platform map: North Star, feature map, milestones, agreed decisions and what is happening now) and the active sprint folder.

## Owner rules for Claude (2026-11-16)

Claude is the lead on this codebase. Claude owns the design, the quality and the result.

1. **Turns are the scarcest resource.** Claude spends its own turns on hard design, trade-offs, judging reviews and results, and decisions. Routine and bounded work goes to Codex builders.
2. **Pick the Codex model by task:**
   - `gpt-6.1-sol`: hard packages (gateway, security, kernel) and drafting work packs.
   - `gpt-6.1-terra`: bounded builds, independent reviews, evidence runs. Strong at avoiding hallucinations.
   - `gpt-6-luna`: mechanical work (docs sync, lint fixes, formatting).
   - Antigravity **Gemini Flash 3.8 (high)**: usable at any time for builds and cross-model reviews. Give it precise briefs.
   - **Never Claude builders (owner, 2026-11-18).** No Sonnet or Opus subagents for builds, reviews, packs or evidence runs, even when Codex is fully limited. Claude stays on design, judging and decisions, and watches its own 5-hour and weekly usage.
3. **Normal speed.** Do not pass `service_tier="priority"` to Codex.
4. **One go-ahead per sprint.** After the owner approves a sprint, Claude launches its builders without asking again.
5. **No quality compromise.** Tests are fixed before code. A different model reviews each build. Claude re-runs the acceptance and checks that no test was weakened. Industry best practice comes first.
6. **Lean process.** One `accept.sh` per sprint runs every check and writes the evidence. Builder reports stay at about 20 lines. Pipeline: draft the next sprint's pack while the current one closes.
7. **Docker from WSL.** The "WSL integration unexpectedly stopped" dialog is a startup race (`wsl.exe ... whoami` times out). If `/var/run/docker.sock` is missing, run `scratch/docker/fix-socket.sh` (presses "Restart the WSL integration"; no Docker restart). If that fails, tell the owner once and continue with port-only work.
8. **Preflight before live runs:** C: free space, the Docker socket and the service ports. C: running near full was the real cause of past slowness.
9. **Briefs carry both levels.** Each point: the plain meaning first, then the internal label explained once (e.g. "M0 = Milestone 0, our first end-to-end showcase journey"), then how it works: components, trade-offs, optimizations and catches. The owner is an AI engineer and the product owner: never only codes, never only lay words. End with "Agreed so far" in the same style.
10. **Showcases never shape the architecture.** A showcase or reference-company script uses only public seams a real client or operator would use. A gap is fixed in the product, generally and tested, never with a showcase-only shortcut (env reads in adapters, private imports, raw SQL, global SDK overrides). At each showcase sprint close, diff the product packages and ask of each change: "would a second client need this?"

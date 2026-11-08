# Deployment Sprint Plan

Two roles. Do not blend them.

**Architect** (this file, already written, not yours to rewrite): defines every
task, its exact scope, and its Definition of Done. The task list below is
final. Do not add tasks, do not reorder them, do not expand a task's scope
while working it, do not write your own plan document.

**Builder** (you): execute exactly ONE task at a time, in order. After each
task, stop, report what changed in 2-3 sentences, and wait. Do not chain
into the next task without the user telling you to continue. Do not fix
things outside the current task's file list, even if you notice them, note
it instead and move on.

Hard rules, apply to every task below:
- Touch only the files listed for that task. Nothing else.
- No refactors, no "while I'm here" cleanup, no new abstractions.
- Never commit or push unless the user explicitly says to.
- Commit style when asked: `type(scope): description`, lowercase, imperative,
  subject line only, no body, no Co-Authored-By trailer. Run
  `git log --oneline -10` first and match it exactly.
- Never write an API key or connection string into any tracked file. `.env`
  is gitignored, put secrets there only.
- Creating or modifying a cloud resource (Render service, dashboard config)
  needs the user's explicit go-ahead first. Read-only checks (curl, git log,
  health checks) don't.
- API calls that cost real tokens against a real provider (Gemini, Groq)
  are not free actions. Make one calculated call when a task actually
  requires verifying something, never call an LLM API speculatively, never
  retry a failed call more than once without asking the user first, and
  never make a call just to "see what happens."
- Branch is `deploy/koyeb-demo`. Confirm you're on it before task 1.

Current state going in: backend is live at
`https://ai-platform-6udm.onrender.com`, `/health` returns all-ok,
`/search` returns real cited answers. `/agent/query` works but can hit
Groq's free-tier 8000 TPM rate limit on multi-step questions, that's why
Task 3 below moves completion off Groq entirely. Frontend (`ui/`) has
never been deployed, only run locally.

---

## Task 1 — Confirm environment (read-only)

Run:
```
git branch --show-current
git status --short
curl -s https://ai-platform-6udm.onrender.com/health
```
**Done when:** branch is `deploy/koyeb-demo`, working tree is clean or shows
only expected untracked files, health check returns `"status":"ok"`. Report
the three outputs. Do not fix anything here, this is a status check only.

## Task 2 — Verify the spare Gemini key (one calculated call, already done)

The user gave a second Gemini API key, saved in `.env` as
`GEMINI_API_KEY_BACKUP`. It has already been verified working (confirmed
directly against `generativelanguage.googleapis.com/v1beta/models`, got a
real model list back, model catalog included current-gen Gemini models).
Do not re-verify it, that call has already been spent. Just confirm it's
present in `.env` (`grep GEMINI_API_KEY_BACKUP .env`, read-only, no API
call) and move on.

**Done when:** you've confirmed the line exists in `.env`. No network call
in this task.

## Task 3 — Move demo-mode LLM completion from Groq to Gemini

File: `config.py` only, the `LLM_CONFIG["model"]` dict.

Groq's free tier caps at 8000 tokens/minute, which the agent's multi-step
flow can exceed on a single request. Gemini's flash-lite tier has
historically had the most generous free-tier rate limits of any model in
Gemini's current lineup (it's Google's lowest-latency, lowest-cost class,
built for high-volume use, not the reasoning-heavy pro tier). We already
depend on Gemini for embeddings, so this removes a provider dependency
rather than adding one.

Change:
```python
"local": "groq/openai/gpt-oss-120b", # For complex reasoning
"demo":  "groq/openai/gpt-oss-120b",
"prod":  "azure/gpt-4o",
}.get(MODE, "groq/openai/gpt-oss-120b")),
```
to:
```python
"local": "gemini/gemini-2.5-flash-lite",
"demo":  "gemini/gemini-2.5-flash-lite",
"prod":  "azure/gpt-4o",
}.get(MODE, "gemini/gemini-2.5-flash-lite")),
```
Leave the `"prod"` line untouched. Leave `MODEL_PRICING` in this file
alone too, that's a separate concern, not this task.

Do not remove `GROQ_API_KEY` from `render.yaml`, `.env`, or anywhere else
in this task, that's out of scope here. Do not make any Gemini API call to
"test" this change, the key already works (Task 2) and functional
verification only makes sense after this is actually deployed, which
needs the user's go-ahead (see hard rules above).

**Done when:** the three model strings are changed, nothing else in the
file is touched. Report the diff and stop, ask the user before committing.

## Task 4 — Fix the Vite build-arg bug

File: `ui/Dockerfile.ui` only.

The Dockerfile declares `ARG VITE_API_URL` but never exports it as an
environment variable before `RUN npm run build`, so Vite's
`import.meta.env.VITE_API_URL` is always undefined in the built output,
regardless of what build arg is passed. Add one line,
`ENV VITE_API_URL=$VITE_API_URL`, between the `ARG` line and the
`RUN npm run build` line.

**Done when:** that one line is added, nothing else in the file changes.
Do not touch `nginx.conf` or any other file in this task.

## Task 5 — Add a configurable CORS origin

File: `api/main.py` only, specifically the `CORSMiddleware` block (currently
`allow_origins` is a hardcoded list of three `localhost` entries).

Add one more origin to that list, read from an environment variable, e.g.:
```python
allow_origins=[
    "http://localhost:5173",
    "http://localhost:4173",
    "http://localhost:3000",
    *([os.environ["FRONTEND_URL"]] if os.environ.get("FRONTEND_URL") else []),
],
```
(adapt to match the existing import style in the file, `os` may already be
imported). Do not restructure the middleware stack, do not change ordering,
do not touch any other middleware.

**Done when:** the list conditionally includes an extra origin from
`FRONTEND_URL` if set, with zero behavior change when it's unset.

## Task 6 — Add the frontend service to render.yaml

File: `render.yaml` only. Do not touch the existing `ai-platform` service
block, only add a second entry to the `services:` list.

```yaml
  - type: web
    name: ai-platform-ui
    runtime: docker
    dockerfilePath: ./ui/Dockerfile.ui
    dockerContext: ./ui
    plan: free
    dockerBuildArgs:
      VITE_API_URL: https://ai-platform-6udm.onrender.com
```
(Check Render's current blueprint spec for the exact key name for build args,
it may be `dockerBuildArgs` or nested differently, verify against
https://render.com/docs/blueprint-spec before committing to a key name, don't
guess if the docs show something different.)

**Done when:** `render.yaml` parses as valid YAML and has exactly two
services defined. Do not deploy anything yet, this task is just the file.

## Task 7 — Stop and hand back to the user

Do not create or sync any Render service yourself, and do not commit or
push Tasks 3-6 yourself. Show the user the diffs from Tasks 3-6, ask if
they want them committed and pushed, then tell them exactly what to click
in Render: existing Blueprint → Sync (picks up both the model change and
the new frontend service). Wait for them to report back the new frontend
service's live URL.

## Task 8 — Wire the real frontend URL through

Once the user gives you the live frontend URL:
1. In the Render dashboard (tell the user how, or do it via API only if
   they've explicitly authorized that), set `FRONTEND_URL` on the backend
   service (`ai-platform`) to that URL, so Task 5's CORS change takes effect.
2. Verify: `curl -s -o /dev/null -w "%{http_code}" <frontend-url>` returns
   200.
3. Ask the user to open the frontend URL in a browser and try a real search,
   confirm it returns results with no CORS error in the browser console.

**Done when:** the user confirms the search works from the deployed
frontend. Do not move to task 9 without that confirmation.

## Task 9 — One-line README update

File: `README.md` only. Add a short "Live Demo" section above "Getting
Started", both URLs (backend + frontend), one sentence noting `MODE=demo`
means reranker is off and completion runs on Gemini flash-lite rather than
Groq. Match the existing terse style in the file, no em dashes, no new
headers beyond that one section, don't touch anything else in the file.

**Done when:** that section exists and nothing else in README.md changed.

---

**Stop after Task 9.** Do not propose further tasks, improvements, or a
"phase 2" plan. Report final state: both live URLs, health status, and
confirmation the LLM swap resolved the earlier Groq rate-limit failure.

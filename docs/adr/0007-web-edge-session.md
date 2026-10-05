# ADR 0007: The web edge session

**Status:** Accepted

## Context
The web client needs to sign in without holding a long-lived API key in the browser. The old UI sent a preview key that nginx injected, and a key kept in JavaScript can be stolen by any script on the page.

RFC 10017 (browser-based apps) recommends keeping tokens on the server and giving the browser only an opaque session cookie. The usual way to do this is a separate backend-for-frontend (BFF) service. With one web client, a separate service is not worth its cost: another deploy, another hop, and another place to get auth wrong. The API already knows how to verify a key and how to build a `Principal`.

## Decision
A thin web edge inside the monolith, in `api/web_edge/`. It is not a new service.
- **Sign in.** `POST /v1/session` takes an API key, verifies it once, and creates a session. The key is never stored. `POST /v1/session/preview` starts an automatic read-only session for one configured principal (`PREVIEW_PRINCIPAL_ID`), only when `MODE=public-preview`. `GET /v1/session` reads the session. `DELETE /v1/session` ends it.
- **Session store.** Redis, under `websess:<sha256(session id)>`. The value holds the principal id, tenant id, scopes, a CSRF token, the creation time, a preview flag and the prefix of the key used to sign in (a public identifier, null for preview). It holds no key secret or hash. The id is 32 random bytes, and only its hash is a Redis key. The TTL is 8 hours and slides on use, with an absolute cap of 24 hours.
- **Cookie.** `gap_session`, HttpOnly, SameSite=Strict, Path=/, and Secure unless `MODE=local`.
- **Auth order.** `AuthMiddleware` tries a bearer key or JWT first. With no bearer it tries the cookie. Otherwise the answer is 401. A cookie session becomes the same `Principal` a key gives, so `enforce()`, policies and row-level security do not change. The principal row is checked on every request, so disabling a principal ends its sessions. The sign-in key is checked on every request too (`auth_lookup_key`, no new migration): once it is revoked, or no longer belongs to the principal, the session is deleted and the cookie gets 401. A preview session needs its principal to still have an unrevoked key (`auth_lookup_preview`). Scopes are a snapshot taken at sign-in, so a scope change on a key needs a new sign-in (a live session keeps its old scopes until it expires: 8 h sliding, 24 h cap).
- **CSRF.** With a cookie session, every method except GET, HEAD and OPTIONS needs an `X-CSRF-Token` header equal to the session's token, or the answer is 403 `csrf_failed`. `DELETE /v1/session` checks it whenever a session cookie is sent, even next to a bearer header. Bearer requests need no token, because a browser does not attach a bearer header on its own.
- **Preview is read-only.** The preview session takes the scopes of the preview principal's unrevoked keys and always removes `kb:write` and `admin`. `PREVIEW_PRINCIPAL_ID` is validated as a UUID and is refused when `MODE=prod`.
- **Preview lookup.** The setting holds only a principal id, and the lookup runs before any tenant is known. Migration `0006` adds one narrow SECURITY DEFINER function, `auth_lookup_preview`, in the same audited pattern as `auth_lookup_key` and `auth_lookup_principal`. It creates no table.
- **Sign-in rate limit.** 10 attempts per minute per client IP (Redis, key `rl:ip:signin:<ip>:<window>`), not per principal, because the caller has no principal yet.
- **Fail closed.** If Redis or the database fails while resolving or creating a session, the answer is 503, never an allow.

## Revisit when
- A mobile app arrives, because it can hold a token in secure storage and may want a different flow.
- A second web client or another origin arrives, because the cookie and CSRF design assume one same-site client.
- Server-side rendering arrives, because the render server would need to act for the user.

Then a separate BFF becomes worth its cost, and this module is the part that moves.

## Consequences
- The browser never sees an API key after sign-in. A stolen cookie is limited by its TTL, by the absolute cap, and by CSRF and SameSite, and it can be ended by deleting the session or disabling the principal.
- Every cookie request costs one Redis read and one small database lookup. Bearer requests cost nothing extra.
- Redis is now needed to sign in. A Redis outage blocks browser sessions (503) but not bearer clients, except where the gateway already needs Redis.
- Sessions snapshot scopes at sign-in. A change to a key's scopes does not reach a live session. It applies at the next sign-in. The principal being disabled applies at once.
- The sign-in limit uses the socket address of the client. Behind a proxy that address is the proxy, so every visitor would share one budget. A trusted-proxy setting for the forwarded address is not built yet (see `planning/QUESTIONS.md`).
- The preview session is as powerful as the preview principal's read scopes. Choose that principal with care.

## Alternatives considered
- **A separate BFF service:** the cleanest split, but too much for one client. It stays the answer for the revisit cases above.
- **Keep the key in the browser (memory or storage):** simplest, but any script on the page can steal a long-lived key.
- **A signed cookie or JWT with no server store:** no Redis, but a session cannot be ended early and its contents sit in the browser.
- **The nginx key injection:** a shared key for every visitor, with no identity, no logout and no per-user audit. It is removed with the old UI.

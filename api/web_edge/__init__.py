"""The web edge (ADR-0007): browser sessions for the web client, inside the API process.

A session lives in Redis and holds the principal, tenant, scopes and a CSRF token, never a key. The browser
holds only an opaque, HttpOnly cookie. `api/middleware/auth.py` resolves the cookie to the same `Principal` a
key gives, so `enforce()` and row-level security do not change.
"""

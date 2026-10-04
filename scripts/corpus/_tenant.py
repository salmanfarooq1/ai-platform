"""Tenant for the offline corpus scripts. Not shipped.

Ingestion is tenant-scoped now (Sprint 003): rows belong to one tenant and row-level security hides them
from every other. The scripts connect as the app role, so they need to be told whose corpus they build:

    export CORPUS_TENANT_ID=<tenant uuid>      # printed by scripts/admin/identity.py create-tenant
"""
import os
import sys
from uuid import UUID


def corpus_tenant_id() -> UUID:
    raw = os.environ.get("CORPUS_TENANT_ID", "")
    try:
        return UUID(raw)
    except ValueError:
        sys.exit("Set CORPUS_TENANT_ID to the tenant's UUID (see scripts/admin/identity.py create-tenant).")

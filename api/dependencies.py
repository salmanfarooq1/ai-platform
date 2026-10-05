from fastapi import Request

from core.database.tenant import DbPool
from ports import Adapters


# define a dependency function to get the database pool from the app state
# so that it is created once and shared across all requests, not created for each request.
async def get_db_pool(request: Request) -> DbPool:
    pool: DbPool = request.app.state.db_pool
    return pool


def adapters_of(request: Request) -> Adapters:
    """The ports of this app, built once at startup by `adapters/registry.py`."""
    adapters: Adapters = request.app.state.adapters
    return adapters

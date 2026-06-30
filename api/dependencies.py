from fastapi import Request
from asyncpg import Pool

# define a dependency function to get the database pool from the app state
# so that it is created once and shared across all requests, not created for each request.
async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool
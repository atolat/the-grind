import asyncpg

# Connection pool - reuse connections instead of creating new ones
# (Remember our connection pooling deep dive!)
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            user="kvstore",
            password="kvstore123",
            database="kvstore",
            min_size=5,
            max_size=20,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

iimport time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.db import close_pool, get_pool
from app.models import ErrorResponse, KVResponse, PutRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create pool. Shutdown: close pool."""
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="KV Store", lifespan=lifespan)


def _now() -> int:
    """Current time as Unix epoch (seconds)."""
    return int(time.time())


# ---------------------------------------------------------------------------
# PUT /keys/{key}
# ---------------------------------------------------------------------------
@app.put("/keys/{key}", response_model=KVResponse)
async def put_key(key: str, body: PutRequest):
    """Insert or update a key-value pair with optional TTL."""
    pool = await get_pool()

    # Calculate absolute expiration from relative TTL
    # expire_at = 0 means "never expires"
    expire_at = (_now() + body.ttl) if body.ttl else 0

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO kv_store (key, value, expire_at) VALUES ($1, $2, $3) ON CONFLICT (key) DO UPDATE SET value = $2, expire_at = $3",
            key,
            body.value,
            expire_at,
        )
        pass

    return KVResponse(key=key, value=body.value)


# ---------------------------------------------------------------------------
# GET /keys/{key}
# ---------------------------------------------------------------------------
@app.get(
    "/keys/{key}",
    response_model=KVResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_key(key: str):
    """Retrieve a key's value. Returns 404 if key doesn't exist or is expired."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # TODO (Arpan): Write the SELECT query
        # - Only return the key if it exists AND is not expired
        # - Remember: expire_at=0 means "never expires"
        # - What should the WHERE clause look like?
        row = None  # Replace with actual query

    if row is None:
        raise HTTPException(status_code=404, detail="Key not found")

    return KVResponse(key=row["key"], value=row["value"])


# ---------------------------------------------------------------------------
# DELETE /keys/{key}
# ---------------------------------------------------------------------------
@app.delete("/keys/{key}")
async def delete_key(key: str):
    """Soft-delete a key by setting expire_at = -1."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # TODO (Arpan): Write the soft DELETE query
        # - Don't hard delete! Set expire_at = -1
        # - Only delete if the key is currently alive
        # - What does "currently alive" mean in terms of expire_at?
        result = None  # Replace with actual query

    # TODO (Arpan): How do you check if the UPDATE affected any rows?
    # If no rows were affected, the key didn't exist — return 404

    return {"status": "deleted", "key": key}

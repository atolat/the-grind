import time
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
            "INSERT INTO store (key, value, expire_at) VALUES ($1, $2, $3) ON CONFLICT (key) DO UPDATE SET value = $2, expire_at = $3",
            key,
            body.value,
            expire_at,
        )

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
        row = await conn.fetchrow(
            "SELECT key, value FROM store WHERE key = $1 AND (expire_at > $2 OR expire_at = 0)",
            key,
            _now(),
        )
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
        result = await conn.execute(
            "UPDATE store SET expire_at = -1 WHERE key = $1 AND (expire_at > $2 OR expire_at = 0)",
            key,
            _now(),
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "success"}
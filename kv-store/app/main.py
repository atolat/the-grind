"""
KV Store — FastAPI Application
===============================

A distributed key-value store built on PostgreSQL with:
- Read/write splitting (writes → primary, reads → replicas)
- TTL-based key expiration
- Soft deletes (expire_at = -1)
- Background cleanup of expired/deleted rows
- Consistent read support via ?consistent=true

Architecture:
    Client → FastAPI (async, single-threaded event loop)
        ├── PUT/DELETE → primary pool (port 5432)
        ├── GET        → replica pool (round-robin 5433/5434)
        └── cleanup    → primary pool (background asyncio task)
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.db import close_pools, get_primary_pool, get_replica_pool, init_pools
from app.models import ErrorResponse, KVResponse, PutRequest

logger = logging.getLogger(__name__)

# Cleanup configuration
# In production, CLEANUP_INTERVAL_SECONDS should be 60+ seconds.
# We use 10 here for demo purposes so we can observe the cleanup quickly.
CLEANUP_INTERVAL_SECONDS = 10
CLEANUP_BATCH_SIZE = 1000  # max rows to delete per run (prevents long-running locks)


# ---------------------------------------------------------------------------
# Background cleanup task
# ---------------------------------------------------------------------------
async def cleanup_loop():
    """
    Periodically hard-delete expired and soft-deleted rows.

    Why a background task instead of deleting on read?
    - Deleting on read adds latency to GET requests
    - Batch deletes are more efficient (fewer transactions)
    - Keeps read path simple and fast

    How it integrates with the event loop:
    - Runs as an asyncio.Task on the SAME event loop as request handlers
    - asyncio.sleep() SUSPENDS this coroutine (doesn't block the thread)
    - Other requests continue being served while this task sleeps
    - When it wakes up, it runs between request-handling coroutines

    Think of it as: the event loop has a to-do list. This task adds itself
    back to the list every 10 seconds. Between those 10-second naps,
    request handlers get their turns.
    """
    while True:
        # await = "suspend me for 10 seconds, let the event loop serve requests"
        # NOT time.sleep(10) which would BLOCK the entire thread!
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

        try:
            pool = get_primary_pool()  # cleanup = write operation = must use primary

            # async with = "acquiring a connection may involve I/O (opening TCP
            # connection or waiting for a free slot). Suspend if needed so the
            # event loop can serve requests while we wait."
            async with pool.acquire() as conn:
                # Delete rows where:
                #   • expire_at > 0 and expire_at <= now → TTL expired
                #   • expire_at = -1                     → soft-deleted
                #
                # The single condition (expire_at != 0 AND expire_at <= now)
                # catches BOTH cases because -1 is always <= current epoch.
                #
                # Why the ctid subquery?
                # PostgreSQL does NOT support DELETE ... LIMIT (MySQL does).
                # We use ctid (physical row address) to batch the deletes:
                #   1. Inner SELECT finds up to BATCH_SIZE expired row addresses
                #   2. Outer DELETE removes exactly those rows
                # This prevents locking 500K rows at once in a big table.
                result = await conn.execute(
                    """
                    DELETE FROM store
                    WHERE ctid IN (
                        SELECT ctid FROM store
                        WHERE expire_at != 0 AND expire_at <= $1
                        LIMIT $2
                    )
                    """,
                    int(time.time()),
                    CLEANUP_BATCH_SIZE,
                )
                # asyncpg returns status strings like "DELETE 42"
                deleted = int(result.split()[-1])
                if deleted > 0:
                    logger.info(f"Cleanup: deleted {deleted} expired/soft-deleted rows")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            # Don't crash the loop — just log and retry next cycle.
            # The while True will continue, and we'll try again in 10 seconds.


# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager — runs once at startup and shutdown.

    This is an async context manager (uses `async with` internally):
      • __aenter__: everything before `yield` runs at STARTUP
      • __aexit__:  everything after `yield` runs at SHUTDOWN

    The `yield` is what makes this a context manager — it "pauses" the
    lifespan function and lets the app run. When the app shuts down,
    execution resumes after the yield for cleanup.
    """
    # ── STARTUP ──────────────────────────────────────────────────────
    await init_pools()  # create primary + replica connection pools

    # asyncio.create_task() schedules cleanup_loop() on the event loop.
    # It starts running immediately (well, at the next loop iteration)
    # and continues running alongside request handlers.
    cleanup_task = asyncio.create_task(cleanup_loop())

    yield  # ← app is running, serving requests

    # ── SHUTDOWN ─────────────────────────────────────────────────────
    cleanup_task.cancel()  # signal the task: "stop at your next await"
    try:
        await cleanup_task  # wait for the task to actually stop
    except asyncio.CancelledError:
        pass  # expected — asyncio raises CancelledError in the task
    await close_pools()  # close all database connections


app = FastAPI(title="KV Store", lifespan=lifespan)


def _now() -> int:
    """Current time as Unix epoch (seconds)."""
    return int(time.time())


# ---------------------------------------------------------------------------
# PUT /keys/{key}
# ---------------------------------------------------------------------------
@app.put("/keys/{key}", response_model=KVResponse)
async def put_key(key: str, body: PutRequest):
    """
    Insert or update a key-value pair with optional TTL.

    Uses PostgreSQL UPSERT (INSERT ... ON CONFLICT DO UPDATE):
      - If key doesn't exist → INSERT
      - If key exists         → UPDATE value and expire_at
    Single atomic statement, no transaction needed. ~32x faster than
    REPLACE INTO (which does DELETE + INSERT, triggering reindexing).

    Parameters:
      key  — from URL path (/keys/{key})
      body — from JSON request body (Pydantic validates it)
        • value: str (required)
        • ttl: int | None (optional, seconds until expiration)
    """
    pool = get_primary_pool()  # writes always go to primary

    # Convert relative TTL (seconds from now) to absolute epoch timestamp.
    # expire_at = 0 is our sentinel for "never expires".
    expire_at = (_now() + body.ttl) if body.ttl else 0

    # async with pool.acquire() — get a connection from the pool.
    # If all connections are busy, this SUSPENDS (not blocks) until one
    # is available. The event loop serves other requests while we wait.
    async with pool.acquire() as conn:
        # await conn.execute() — send the query and SUSPEND until Postgres
        # responds. Event loop handles other requests during the ~3-5ms
        # round trip to the database.
        await conn.execute(
            """
            INSERT INTO store (key, value, expire_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (key) DO UPDATE SET value = $2, expire_at = $3
            """,
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
async def get_key(key: str, consistent: bool = False):
    """
    Retrieve a key's value. Returns 404 if key doesn't exist or is expired.

    Read routing:
      • consistent=false (default) → read from a replica (eventually consistent)
      • consistent=true            → read from primary (strongly consistent)

    Why replicas might return stale data:
      Replication is async — there's a small lag (usually <100ms) between
      a write hitting the primary and propagating to replicas. If you PUT
      a key and immediately GET it, the replica might not have it yet.

    The WHERE clause filters out expired and soft-deleted rows at read time,
    even before the cleanup loop hard-deletes them. This means:
      • expire_at = 0  → never expires, always returned
      • expire_at > now → not yet expired, returned
      • expire_at <= now or expire_at = -1 → expired/deleted, NOT returned
    """
    if consistent:
        pool = get_primary_pool()       # strong consistency → primary
    else:
        pool = await get_replica_pool()  # eventual consistency → replica (round-robin)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT key, value FROM store
            WHERE key = $1 AND (expire_at > $2 OR expire_at = 0)
            """,
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
    """
    Soft-delete a key by setting expire_at = -1.

    Why soft delete?
      Hard DELETE on a B+ tree index triggers rebalancing — expensive.
      Setting expire_at = -1 is a cheap UPDATE. The cleanup loop will
      hard-delete it later in a batch (amortizing the rebalancing cost
      across many rows).

    The WHERE clause ensures we only soft-delete keys that are currently
    alive (expire_at > now OR expire_at = 0). No point soft-deleting
    something that's already expired — it's already invisible to reads
    and will be cleaned up anyway.

    asyncpg's execute() returns a status string like "UPDATE 1" or
    "UPDATE 0". We parse the count to detect "key not found".
    """
    pool = get_primary_pool()  # writes always go to primary

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE store SET expire_at = -1
            WHERE key = $1 AND (expire_at > $2 OR expire_at = 0)
            """,
            key,
            _now(),
        )

    # asyncpg returns "UPDATE 0" if no rows matched (key doesn't exist
    # or is already expired/deleted)
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "success"}

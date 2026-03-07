"""
Database Connection Pool Management
====================================

Manages connection pools for a PostgreSQL primary-replica cluster:
  - 1 primary pool   (writes + consistent reads)
  - N replica pools   (eventually-consistent reads, round-robin)

Architecture:
    ┌─────────────────────────┐
    │      FastAPI App        │
    │                         │
    │  get_primary_pool() ────┼──→ Pool (5 min, 20 max connections) → primary:5432
    │                         │
    │  get_replica_pool() ────┼──→ Pool (2 min, 10 max) → replica1:5433
    │        (round-robin)    │──→ Pool (2 min, 10 max) → replica2:5434
    └─────────────────────────┘

Why one pool per host?
  A connection pool holds OPEN TCP connections to a specific host:port.
  Each TCP connection is a socket → (local_ip:local_port, remote_ip:remote_port).
  You can't "redirect" an existing TCP connection to a different server.
  So each PostgreSQL instance needs its own pool.

Lifecycle:
  1. init_pools()       — called once at startup (lifespan __aenter__)
  2. get_*_pool()       — called per-request to get the right pool
  3. close_pools()      — called once at shutdown (lifespan __aexit__)
"""

import itertools
import logging

import asyncpg

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────
# These match the ports exposed in docker-compose.yml
PRIMARY_PORT = 5432
REPLICA_PORTS = [5433, 5434]

DB_CONFIG = {
    "host": "localhost",
    "user": "kvstore",
    "password": "kvstore123",
    "database": "kvstore",
}

# ── Pool state (module-level singletons) ─────────────────────────
# These are initialized ONCE at startup via init_pools() and shared
# across all request handlers. This is safe because:
#   - asyncio is single-threaded (no race conditions)
#   - asyncpg.Pool is designed for concurrent use within one event loop
_primary_pool: asyncpg.Pool | None = None
_replica_pools: list[asyncpg.Pool] = []
_replica_rr: itertools.cycle | None = None  # round-robin index generator


# ── Startup / Shutdown ───────────────────────────────────────────
async def init_pools() -> None:
    """
    Create all connection pools at startup. Called once from lifespan.

    Why async? Because creating a pool involves:
      1. Opening min_size TCP connections to PostgreSQL
      2. Performing the PostgreSQL handshake on each connection
    These are I/O operations → must be awaited.

    Pool sizing:
      - Primary:  min=5, max=20  (handles writes + consistent reads + cleanup)
      - Replicas: min=2, max=10  (lighter load, reads only)
    """
    global _primary_pool, _replica_pools, _replica_rr

    # Primary pool — all writes go here
    _primary_pool = await asyncpg.create_pool(
        **DB_CONFIG, port=PRIMARY_PORT, min_size=5, max_size=20,
    )

    # Replica pools — reads are distributed across these
    for port in REPLICA_PORTS:
        pool = await asyncpg.create_pool(
            **DB_CONFIG, port=port, min_size=2, max_size=10,
        )
        _replica_pools.append(pool)

    # itertools.cycle gives us infinite round-robin: 0, 1, 0, 1, 0, 1, ...
    _replica_rr = itertools.cycle(range(len(_replica_pools)))


async def close_pools() -> None:
    """
    Close all pools on shutdown. Called once from lifespan.

    Closing a pool:
      1. Waits for all checked-out connections to be returned
      2. Sends a graceful disconnect to PostgreSQL on each connection
      3. Closes the underlying TCP sockets
    """
    global _primary_pool, _replica_pools, _replica_rr
    if _primary_pool is not None:
        await _primary_pool.close()
        _primary_pool = None
    for pool in _replica_pools:
        await pool.close()
    _replica_pools = []
    _replica_rr = None


# ── Getters ──────────────────────────────────────────────────────
def get_primary_pool() -> asyncpg.Pool:
    """
    Return the primary pool. Must call init_pools() first.

    Why is this NOT async?
    It just returns a Python variable — no I/O involved.
    The pool already exists (created at startup). Nothing to await.
    """
    assert _primary_pool is not None, "Call init_pools() before using pools"
    return _primary_pool


async def get_replica_pool() -> asyncpg.Pool:
    """
    Round-robin across replicas with health check and fallback.

    Why IS this async? (unlike get_primary_pool)
    Because it does a health check (SELECT 1) on the chosen replica.
    That health check is a database query → I/O → must be awaited.

    Algorithm:
      1. Pick the next replica in round-robin order
      2. Health-check it with SELECT 1
      3. If healthy → return that pool
      4. If unhealthy → try the next replica
      5. If ALL replicas are down → fall back to primary

    The round-robin counter (itertools.cycle) is shared across all
    requests, so load is evenly distributed across replicas.
    """
    if not _replica_pools:
        return get_primary_pool()

    start_idx = next(_replica_rr)

    for i in range(len(_replica_pools)):
        idx = (start_idx + i) % len(_replica_pools)
        pool = _replica_pools[idx]
        try:
            # Health check: can we get a connection and run a trivial query?
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return pool  # healthy — use this replica
        except Exception:
            logger.warning(
                f"Replica {idx} (port {REPLICA_PORTS[idx]}) unavailable, trying next..."
            )

    # All replicas are down — degrade gracefully to primary
    logger.warning("All replicas unavailable, falling back to primary")
    return get_primary_pool()

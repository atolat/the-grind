"""
Connection Pool using a Bounded Queue
======================================

WHY CONNECTION POOLING?
    Opening a DB connection is expensive (TCP handshake, auth, TLS, etc.).
    Instead of open/close per query, we keep a fixed set of connections
    ready in a queue. Callers borrow a connection, use it, then return it.

DATA STRUCTURE: Bounded Queue (queue.Queue)
    - queue.Queue is thread-safe (uses a lock internally).
    - maxsize acts as our pool's upper bound.
    - .get() blocks the caller when the queue is empty (all connections in use).
    - .put() blocks if the queue is full (shouldn't happen if used correctly).

FLOW:
    1. Pool starts by creating N connections and putting them in the queue.
    2. get_conn() pops a connection from the queue (blocks if none available).
    3. release_conn() pushes the connection back into the queue.
    4. close() drains the queue and closes every connection.
"""

import queue
import threading
import time


# ---------------------------------------------------------------------------
# Fake DB connection (stand-in until we wire up a real database)
# ---------------------------------------------------------------------------
class FakeConnection:
    """Simulates a database connection. Replace with a real DB driver later."""

    _counter = 0  # class-level counter to give each connection an id

    def __init__(self):
        FakeConnection._counter += 1
        self.id = FakeConnection._counter
        self.closed = False
        print(f"  [conn-{self.id}] opened")

    def execute(self, sql: str):
        """Pretend to run a query."""
        if self.closed:
            raise RuntimeError(f"conn-{self.id} is closed")
        print(f"  [conn-{self.id}] executing: {sql}")
        time.sleep(0.1)  # simulate query latency
        return f"result from conn-{self.id}"

    def close(self):
        self.closed = True
        print(f"  [conn-{self.id}] closed")


# ---------------------------------------------------------------------------
# Connection Pool
# ---------------------------------------------------------------------------
class ConnectionPool:
    """
    A fixed-size pool backed by a bounded queue.

    Parameters
    ----------
    pool_size : int
        Maximum number of connections the pool will hold.
    connect_fn : callable
        Factory function that returns a new connection object.
    """

    def __init__(self, pool_size: int, connect_fn=None):
        if pool_size <= 0:
            raise ValueError("pool_size must be positive")

        self.pool_size = pool_size
        self._connect_fn = connect_fn or FakeConnection

        # The bounded queue IS the pool.
        # maxsize = pool_size ensures we never exceed our limit.
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)

        # Pre-fill the pool with ready-to-use connections.
        for _ in range(pool_size):
            conn = self._connect_fn()
            self._pool.put(conn)

    # -- public API ---------------------------------------------------------

    def get_conn(self, timeout: float = 5.0):
        """
        Borrow a connection from the pool.

        Blocks up to `timeout` seconds if all connections are in use.
        Raises queue.Empty if no connection becomes available in time.
        """
        try:
            conn = self._pool.get(block=True, timeout=timeout)
            print(f"  [pool] handed out conn-{conn.id}  "
                  f"(available: {self._pool.qsize()}/{self.pool_size})")
            return conn
        except queue.Empty:
            raise TimeoutError(
                f"No connection available within {timeout}s "
                f"(pool size: {self.pool_size})"
            )

    def release_conn(self, conn):
        """Return a connection back to the pool so others can use it."""
        self._pool.put(conn)
        print(f"  [pool] returned  conn-{conn.id}  "
              f"(available: {self._pool.qsize()}/{self.pool_size})")

    def close(self):
        """Drain the pool and close every connection."""
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            conn.close()
        print("  [pool] all connections closed")


# ---------------------------------------------------------------------------
# Demo: multiple threads sharing a small pool
# ---------------------------------------------------------------------------
def worker(pool: ConnectionPool, worker_id: int):
    """Simulates a request handler that needs a DB connection."""
    print(f"Worker-{worker_id}: waiting for a connection...")
    conn = pool.get_conn()

    # Use the connection
    result = conn.execute(f"SELECT * FROM users  -- worker {worker_id}")
    print(f"Worker-{worker_id}: got {result}")

    # ALWAYS return the connection, even on error (try/finally in real code).
    pool.release_conn(conn)


if __name__ == "__main__":
    POOL_SIZE = 2
    NUM_WORKERS = 5

    print(f"=== Creating pool with {POOL_SIZE} connections ===\n")
    pool = ConnectionPool(pool_size=POOL_SIZE)

    print(f"\n=== Launching {NUM_WORKERS} workers (only {POOL_SIZE} can run at once) ===\n")
    threads = []
    for i in range(NUM_WORKERS):
        t = threading.Thread(target=worker, args=(pool, i))
        threads.append(t)
        t.start()

    # Wait for all workers to finish.
    for t in threads:
        t.join()

    print("\n=== Shutting down pool ===\n")
    pool.close()

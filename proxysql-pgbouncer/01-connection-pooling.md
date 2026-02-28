# Connection Pooling

## The Problem

Every database connection is expensive. It involves a TCP handshake, authentication,
and memory allocation on the DB server (~5-10MB per connection in PostgreSQL).

When you have thousands of concurrent users, the database drowns -- not from queries,
but from managing connections. Eventually it hits `max_connections` and rejects everyone.

## What is a Connection Pool?

Instead of open/query/close for every request, a pool keeps a set of connections alive
and reuses them.

```
Without pooling:
  Request 1 → open connection → query → close
  Request 2 → open connection → query → close   (expensive every time)

With pooling:
  Pool holds 20 open connections
  Request 1 → borrow connection → query → return to pool
  Request 2 → borrow connection → query → return to pool   (reuse, no setup cost)
```

## Application-Level Pooling

Most frameworks have built-in pools.

### Python (SQLAlchemy)

```python
from sqlalchemy import create_engine

# pool_size: number of persistent connections kept open
# max_overflow: extra connections allowed beyond pool_size under load
# pool_timeout: seconds to wait for a connection before raising an error
# pool_recycle: seconds before a connection is recycled (helps with DB-side timeouts)
engine = create_engine(
    "postgresql://user:pass@localhost:5432/mydb",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)

# Usage -- the engine handles borrowing/returning automatically
with engine.connect() as conn:
    result = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": 42})
```

### Go (pgxpool)

```go
package main

import (
    "context"
    "fmt"
    "github.com/jackc/pgx/v5/pgxpool"
)

func main() {
    config, _ := pgxpool.ParseConfig("postgresql://user:pass@localhost:5432/mydb")

    // Pool configuration
    config.MaxConns = 20           // maximum number of connections in the pool
    config.MinConns = 5            // minimum idle connections kept open
    config.MaxConnLifetime = 30 * time.Minute  // recycle connections after this
    config.MaxConnIdleTime = 5 * time.Minute   // close idle connections after this

    pool, _ := pgxpool.NewWithConfig(context.Background(), config)
    defer pool.Close()

    // Usage -- pool.Query borrows a connection, uses it, returns it
    var name string
    err := pool.QueryRow(context.Background(),
        "SELECT name FROM users WHERE id = $1", 42,
    ).Scan(&name)
    fmt.Println(name, err)
}
```

## The N * X Problem: Why App Pools Aren't Enough

Each app server manages its pool independently. No server knows about the others.

```
App Server 1  (pool: 20) ──→  20 connections ──┐
App Server 2  (pool: 20) ──→  20 connections ──┤
App Server 3  (pool: 20) ──→  20 connections ──┼──→ Database
...                                            │
App Server 50 (pool: 20) ──→  20 connections ──┘    = 1,000 connections!
```

Most of those connections are idle most of the time, but they're unavailable to other
servers that might need them.

```mermaid
graph LR
    A1[App Server 1<br/>pool: 20] -->|20 conns| DB[(Database)]
    A2[App Server 2<br/>pool: 20] -->|20 conns| DB
    A3[App Server 3<br/>pool: 20] -->|20 conns| DB
    A4[...<br/>App Server N] -->|20 conns| DB
    A5[App Server 50<br/>pool: 20] -->|20 conns| DB
    DB -.- T["50 × 20 = 1,000 connections<br/>most sitting idle"]
    style T fill:none,stroke:none
    style DB fill:#4a1a1a,stroke:#ff6666
```

## Proxy-Level Pooling (PgBouncer / ProxySQL)

A proxy sits between all app servers and the database. It multiplexes many app
connections onto fewer real DB connections.

```
App Server 1  (pool: 5) ──┐
App Server 2  (pool: 5) ──┤
App Server 3  (pool: 5) ──┼──→  PgBouncer (pool: 30) ──→  Database (30 real connections)
...                       │
App Server 50 (pool: 5) ──┘
     250 app connections funneled into 30 real connections
```

This works because not all 250 connections are actively querying at the same instant.
PgBouncer borrows a real connection only for the duration of a query/transaction,
then releases it for someone else.

```mermaid
graph LR
    A1[App Server 1<br/>pool: 5] --> PG[PgBouncer<br/>pool: 30]
    A2[App Server 2<br/>pool: 5] --> PG
    A3[App Server 3<br/>pool: 5] --> PG
    A4[...<br/>App Server N] --> PG
    A5[App Server 50<br/>pool: 5] --> PG
    PG -->|30 real conns| DB[(Database)]
    PG -.- T["250 app conns → 30 DB conns<br/>~88% reduction"]
    style T fill:none,stroke:none
    style PG fill:#1a3a1a,stroke:#66ff66
```

### PgBouncer Configuration (pgbouncer.ini)

```ini
[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
listen_addr = 0.0.0.0

; Pool mode:
;   session     = one backend per client session (least savings, most compatible)
;   transaction = backend shared after each transaction (good balance)
;   statement   = backend shared after each statement (aggressive, breaks multi-stmt txns)
pool_mode = transaction

; Pool sizing
default_pool_size = 30      ; real DB connections per pool
max_client_conn = 1000      ; max app connections accepted
reserve_pool_size = 5       ; extra connections for burst
```

```mermaid
graph TD
    subgraph "Session Mode"
        S1[Client connects] --> S2[Gets dedicated<br/>backend conn]
        S2 --> S3[Keeps it for<br/>entire session]
        S3 --> S4[Released on<br/>disconnect]
    end
    subgraph "Transaction Mode"
        T1[Client sends<br/>BEGIN] --> T2[Gets backend<br/>conn]
        T2 --> T3[Keeps it for<br/>one transaction]
        T3 --> T4[Released on<br/>COMMIT/ROLLBACK]
    end
    subgraph "Statement Mode"
        Q1[Client sends<br/>query] --> Q2[Gets backend<br/>conn]
        Q2 --> Q3[Keeps it for<br/>one statement]
        Q3 --> Q4[Released<br/>immediately]
    end
```

### App Connects to PgBouncer Instead of DB Directly

The only change in your app: point at PgBouncer's port instead of Postgres.

```python
# Python -- just change the port
engine = create_engine(
    "postgresql://user:pass@localhost:6432/mydb",  # 6432 = PgBouncer, not 5432
    pool_size=5,  # smaller app pool since PgBouncer handles the real pooling
)
```

```go
// Go -- same, just change the port
config, _ := pgxpool.ParseConfig("postgresql://user:pass@localhost:6432/mydb")
config.MaxConns = 5  // smaller app pool
```

## App Pool + Proxy Pool Together

In practice most production setups use both:

- **Small app pool** (5-10) for local efficiency (avoids per-request connection to proxy)
- **Proxy pool** (30-100) for global consolidation across all app servers

## PgBouncer vs ProxySQL

| Aspect           | PgBouncer            | ProxySQL               |
|------------------|----------------------|------------------------|
| For which DB?    | PostgreSQL only      | MySQL/MariaDB only     |
| Primary job      | Connection pooling   | Pooling + routing + more |
| Complexity       | Simple, lightweight  | Feature-rich, complex  |
| Extra features   | Minimal              | Query routing, caching, rewriting |
| Config           | INI file             | SQL-like admin interface |

They are NOT competitors -- they serve different database ecosystems.

## Other Similar Tools

- **Odyssey** -- PostgreSQL pooler by Yandex, supports multithreading (PgBouncer is single-threaded)
- **pgcat** -- PostgreSQL pooler in Rust, supports sharding
- **MySQL Router** -- Oracle's official MySQL proxy
- **Amazon RDS Proxy** -- AWS managed pooler for RDS databases

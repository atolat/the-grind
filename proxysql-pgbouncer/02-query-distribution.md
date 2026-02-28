# Query Distribution and Routing

## The Setup

Most databases at scale use replication:

```
                ┌──→  Replica 1 (read-only copy)
Primary ────────┤
(reads + writes)├──→  Replica 2 (read-only copy)
                └──→  Replica 3 (read-only copy)
```

The primary streams changes to replicas. But if the app sends everything to the primary,
the replicas are just insurance. Query distribution sends reads to replicas, writes to
the primary, spreading the load.

## Approach 1: Application-Level Routing (Dumb Way)

You can handle this in code, but it has downsides: every service needs the logic,
server topology is hardcoded, failover is manual.

### Python (SQLAlchemy)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine_primary = create_engine("postgresql://user:pass@primary:5432/mydb")
engine_replica = create_engine("postgresql://user:pass@replica:5432/mydb")

# Manually choose which connection to use
def get_user(user_id):
    """Read operation -- use replica."""
    with Session(engine_replica) as session:
        return session.query(User).filter_by(id=user_id).first()

def create_user(name):
    """Write operation -- use primary."""
    with Session(engine_primary) as session:
        user = User(name=name)
        session.add(user)
        session.commit()
```

### Go

```go
package main

import (
    "context"
    "github.com/jackc/pgx/v5/pgxpool"
)

var (
    primary *pgxpool.Pool
    replica *pgxpool.Pool
)

func init() {
    primary, _ = pgxpool.New(context.Background(), "postgresql://user:pass@primary:5432/mydb")
    replica, _ = pgxpool.New(context.Background(), "postgresql://user:pass@replica:5432/mydb")
}

// Read -- use replica
func GetUser(ctx context.Context, id int) (string, error) {
    var name string
    err := replica.QueryRow(ctx, "SELECT name FROM users WHERE id = $1", id).Scan(&name)
    return name, err
}

// Write -- use primary
func CreateUser(ctx context.Context, name string) error {
    _, err := primary.Exec(ctx, "INSERT INTO users (name) VALUES ($1)", name)
    return err
}
```

## Approach 2: Proxy-Based Routing

The proxy makes routing invisible to the app. The app sends all queries to one endpoint.

```
App  ──→  ProxySQL  ──→  parses SQL  ──→  SELECT?  ──→  Replica
                                     ──→  INSERT?  ──→  Primary
```

```mermaid
flowchart LR
    App[Application] -->|All queries| Proxy[ProxySQL]
    Proxy -->|Parses SQL| Decision{SELECT?}
    Decision -->|Yes| R{FOR UPDATE?}
    Decision -->|No: INSERT<br/>UPDATE/DELETE| Primary[(Primary)]
    R -->|No| Replica[(Replica)]
    R -->|Yes| Primary
```

### How the Proxy Knows Read vs Write

It parses the SQL:

- `SELECT`               → read  → replica
- `INSERT/UPDATE/DELETE`  → write → primary
- `SELECT ... FOR UPDATE` → takes a lock → primary
- Inside `BEGIN...COMMIT` → all goes to primary (mixing servers mid-transaction breaks consistency)

### ProxySQL Query Rules Configuration

ProxySQL uses "hostgroups" -- group 0 is typically primary, group 1 is replicas.
Rules are evaluated top to bottom, first match wins.

```sql
-- Connect to ProxySQL admin interface
-- mysql -u admin -p -h 127.0.0.1 -P 6032

-- Define backend servers
INSERT INTO mysql_servers (hostgroup_id, hostname, port) VALUES
    (0, 'primary.db.internal', 3306),     -- hostgroup 0 = primary (writes)
    (1, 'replica1.db.internal', 3306),    -- hostgroup 1 = replicas (reads)
    (1, 'replica2.db.internal', 3306),
    (1, 'replica3.db.internal', 3306);

-- Define query rules (order matters -- rule_id determines priority)

-- Rule 1: SELECT ... FOR UPDATE always goes to primary
INSERT INTO mysql_query_rules (rule_id, match_pattern, destination_hostgroup, apply)
    VALUES (1, '^SELECT.*FOR UPDATE', 0, 1);

-- Rule 2: All other SELECTs go to replicas
INSERT INTO mysql_query_rules (rule_id, match_pattern, destination_hostgroup, apply)
    VALUES (2, '^SELECT', 1, 1);

-- Rule 3: Everything else (INSERT, UPDATE, DELETE, DDL) goes to primary
-- (This is the default behavior when no rule matches)

-- Apply the configuration
LOAD MYSQL SERVERS TO RUNTIME;
LOAD MYSQL QUERY RULES TO RUNTIME;
SAVE MYSQL SERVERS TO DISK;
SAVE MYSQL QUERY RULES TO DISK;
```

```mermaid
graph TD
    Q[Incoming Query] --> R1{Rule 1:<br/>SELECT...FOR UPDATE?}
    R1 -->|Match| HG0[Hostgroup 0<br/>Primary]
    R1 -->|No match| R2{Rule 2:<br/>SELECT?}
    R2 -->|Match| HG1[Hostgroup 1<br/>Replicas]
    R2 -->|No match| HG0
    HG1 --> Rep1[Replica 1]
    HG1 --> Rep2[Replica 2]
    HG1 --> Rep3[Replica 3]
```

### Load Balancing Across Replicas

When multiple replicas exist in a hostgroup, ProxySQL distributes reads:

```sql
-- Weight-based distribution
-- replica1 gets 50% of reads, replica2 gets 30%, replica3 gets 20%
INSERT INTO mysql_servers (hostgroup_id, hostname, port, weight) VALUES
    (1, 'replica1.db.internal', 3306, 500),
    (1, 'replica2.db.internal', 3306, 300),
    (1, 'replica3.db.internal', 3306, 200);
```

Other strategies: round-robin, least connections.

## The Big Gotcha: Replication Lag

Replicas are not instant copies. There's a delay -- usually milliseconds, but under
load it can be seconds.

```
App writes:  INSERT INTO users (name) VALUES ('Alice')   →  Primary
App reads:   SELECT * FROM users WHERE name = 'Alice'    →  Replica
                                                              ↑
                                                        Alice isn't here yet!
```

User creates an account, immediately gets "user not found." This is called
read-after-write inconsistency.

```mermaid
sequenceDiagram
    participant App
    participant Proxy
    participant Primary
    participant Replica
    App->>Proxy: INSERT INTO users ('Alice')
    Proxy->>Primary: INSERT INTO users ('Alice')
    Primary-->>Proxy: OK
    Proxy-->>App: OK
    Primary-)Replica: Replication stream (async)
    App->>Proxy: SELECT * WHERE name='Alice'
    Proxy->>Replica: SELECT (routed as read)
    Replica-->>Proxy: Empty result (not replicated yet!)
    Proxy-->>App: User not found
    Note over Primary,Replica: Replication lag causes<br/>read-after-write inconsistency
```

### How Proxies Handle Lag

**Lag-aware routing** -- ProxySQL monitors replica lag:

```sql
-- Don't send reads to replicas that are more than 1 second behind
UPDATE mysql_servers SET max_replication_lag = 1 WHERE hostgroup_id = 1;
```

**Session stickiness** -- after a write, route that session's reads to primary briefly.

**App hints** -- the app marks certain reads as "must go to primary" (see next file).

## PostgreSQL: Combining Tools

Since PgBouncer doesn't route, Postgres setups that need both pooling and
distribution often stack tools:

```
                    ┌──→  PgBouncer  ──→  Primary
App  ──→  HAProxy  ─┤
                    ├──→  PgBouncer  ──→  Replica 1
                    └──→  PgBouncer  ──→  Replica 2
```

HAProxy handles distribution, PgBouncer handles pooling on each node.

Newer tools like pgcat and Odyssey try to do both in one tool.

## Query-Aware Proxy vs Generic Load Balancer

| Capability               | ProxySQL (query-aware) | HAProxy (generic LB) |
|--------------------------|------------------------|----------------------|
| Parse SQL?               | Yes                    | No                   |
| Read/write split?        | Yes                    | No (need separate endpoints) |
| Track transactions?      | Yes                    | No                   |
| Monitor replication lag? | Yes                    | No                   |
| Route by query pattern?  | Yes                    | No                   |

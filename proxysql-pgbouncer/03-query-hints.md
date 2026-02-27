# Query Hints and ORM Integration

## The Problem

The proxy routes queries based on pattern matching, but sometimes the app knows
context the proxy can't infer. Hints let the app guide the proxy.

## How Hints Work

Hints are SQL comments embedded in the query. The DB ignores them, but the proxy
pattern-matches on them.

```sql
/* force-primary */ SELECT * FROM users WHERE id = 42;
```

ProxySQL rule to match:

```sql
INSERT INTO mysql_query_rules (rule_id, match_pattern, destination_hostgroup, apply)
    VALUES (0, '/\* force-primary \*/', 0, 1);
```

## Adding Hints via ORMs

### Python (SQLAlchemy)

```python
from sqlalchemy import select, text

# Using prefix_with to add a comment before the SELECT
stmt = select(User).where(User.id == 42).prefix_with(text("/* force-primary */"))
result = session.execute(stmt)

# For raw-ish queries
result = session.execute(
    text("/* force-primary */ SELECT * FROM users WHERE id = :id"),
    {"id": 42}
)
```

### Go (no ORM, using pgx directly)

```go
// Go doesn't typically use heavy ORMs. With pgx, just prepend the comment.
row := pool.QueryRow(ctx,
    "/* force-primary */ SELECT name FROM users WHERE id = $1", 42,
)
```

### Go (with sqlc or similar generators)

```sql
-- In your .sql query file, add the comment directly
-- name: GetUserForcePrimary :one
/* force-primary */ SELECT name FROM users WHERE id = $1;
```

## The More Common Approach: Separate Connections

In practice, most teams don't sprinkle hints everywhere. Instead they configure
two connections and pick the right one.

### Python (Django Database Router)

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'primary.db.internal',
    },
    'replica': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'replica.db.internal',
    },
}

# routers.py
class ReadReplicaRouter:
    def db_for_read(self, model, **hints):
        return 'replica'

    def db_for_write(self, model, **hints):
        return 'default'

# Override for specific cases where you need read-after-write consistency
User.objects.using('default').get(id=42)  # force read from primary
```

### Python (SQLAlchemy with routing)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine_rw = create_engine("postgresql://user:pass@primary:5432/mydb")
engine_ro = create_engine("postgresql://user:pass@replica:5432/mydb")

# Read from replica
with Session(engine_ro) as session:
    user = session.query(User).filter_by(id=42).first()

# Write to primary
with Session(engine_rw) as session:
    session.add(User(name="Alice"))
    session.commit()

# Read-after-write: explicitly use primary for the read
with Session(engine_rw) as session:
    user = session.query(User).filter_by(name="Alice").first()
```

### Go (two pools)

```go
primary, _ := pgxpool.New(ctx, "postgresql://user:pass@primary:5432/mydb")
replica, _ := pgxpool.New(ctx, "postgresql://user:pass@replica:5432/mydb")

// Normal read -- use replica
replica.QueryRow(ctx, "SELECT name FROM users WHERE id = $1", 42)

// Read-after-write -- use primary
primary.Exec(ctx, "INSERT INTO users (name) VALUES ($1)", "Alice")
primary.QueryRow(ctx, "SELECT * FROM users WHERE name = $1", "Alice")  // guaranteed to see Alice
```

## Auto-Commenting for Observability

Instead of routing hints, many teams auto-tag queries with metadata for debugging.
When a slow query shows up in DB logs, you immediately know where it came from.

### Python (sqlcommenter with SQLAlchemy)

```python
# pip install opentelemetry-sqlcommenter

# Automatically adds comments like:
# SELECT * FROM users WHERE id = 1
#   /* app=myservice, endpoint=/api/users, request_id=abc123 */
```

### Go (manual approach)

```go
func queryWithContext(ctx context.Context, pool *pgxpool.Pool, query string, args ...any) pgx.Row {
    requestID := ctx.Value("request_id")
    tagged := fmt.Sprintf("/* request_id=%s */ %s", requestID, query)
    return pool.QueryRow(ctx, tagged, args...)
}
```

## What Most Teams Actually Do

1. ORM-level read/write split using two connections (or a router)
2. Proxy handles pooling and load balancing across replicas
3. Hints used sparingly for edge cases (read-after-write)
4. Auto-commenting for observability, not routing

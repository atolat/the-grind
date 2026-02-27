# Prepared Statements vs Database Functions

## Prepared Statements

Normally every query goes through: Parse → Plan → Execute.
A prepared statement splits this so you parse/plan once, execute many times.

### Python (SQLAlchemy)

SQLAlchemy uses parameterized queries by default. The driver handles preparation.

```python
from sqlalchemy import text

# This is parameterized -- value is sent separately from SQL structure.
# The driver decides whether to use server-side prepared statements.
result = session.execute(
    text("SELECT * FROM users WHERE id = :id"),
    {"id": 42}
)

# psycopg (the underlying driver) can do explicit server-side prepared statements:
import psycopg

with psycopg.connect("postgresql://user:pass@localhost/mydb") as conn:
    # prepare() creates a server-side prepared statement
    stmt = conn.execute(
        "SELECT * FROM users WHERE id = %s", [42],
        prepare=True,
    )
    # Subsequent calls with the same SQL reuse the prepared plan
    conn.execute("SELECT * FROM users WHERE id = %s", [99], prepare=True)
```

### Go (pgx)

```go
// pgx automatically uses prepared statements in certain modes.

// Explicit prepared statement:
conn, _ := pool.Acquire(ctx)
defer conn.Release()

// Prepare once
_, err := conn.Conn().Prepare(ctx, "get_user", "SELECT name FROM users WHERE id = $1")

// Execute many times -- skips parsing/planning each time
var name string
conn.QueryRow(ctx, "get_user", 42).Scan(&name)
conn.QueryRow(ctx, "get_user", 99).Scan(&name)
conn.QueryRow(ctx, "get_user", 7).Scan(&name)
```

### Why Prepared Statements Matter

**Performance**: skip repeated parse/plan overhead for queries run thousands of times.

**SQL injection prevention**: the value is sent separately from the SQL structure.

```python
# DANGEROUS -- string interpolation, vulnerable to injection
query = f"SELECT * FROM users WHERE name = '{user_input}'"
# user_input = "'; DROP TABLE users; --"  → catastrophe

# SAFE -- parameterized, value can never be interpreted as SQL
session.execute(text("SELECT * FROM users WHERE name = :name"), {"name": user_input})
# user_input = "'; DROP TABLE users; --"  → treated as a literal string
```

```go
// DANGEROUS
query := fmt.Sprintf("SELECT * FROM users WHERE name = '%s'", userInput)

// SAFE
pool.QueryRow(ctx, "SELECT * FROM users WHERE name = $1", userInput)
```

## Database Functions (Stored Procedures)

Completely different. These are permanent code stored in the database.

### PostgreSQL Function

```sql
CREATE FUNCTION get_active_users(min_age INT)
RETURNS TABLE(id INT, name TEXT) AS $$
BEGIN
    RETURN QUERY
        SELECT u.id, u.name
        FROM users u
        WHERE u.active = true
        AND u.age >= min_age;
END;
$$ LANGUAGE plpgsql;
```

### Calling from Python

```python
result = session.execute(text("SELECT * FROM get_active_users(:age)"), {"age": 21})
for row in result:
    print(row.id, row.name)
```

### Calling from Go

```go
rows, _ := pool.Query(ctx, "SELECT * FROM get_active_users($1)", 21)
defer rows.Close()
for rows.Next() {
    var id int
    var name string
    rows.Scan(&id, &name)
    fmt.Println(id, name)
}
```

## Side by Side Comparison

| Aspect                    | Prepared Statement              | Database Function               |
|---------------------------|----------------------------------|----------------------------------|
| Stored where?             | Connection memory (temporary)    | Database catalog (permanent)     |
| Created by?               | App/driver automatically         | Developer/DBA deliberately       |
| Contains logic?           | No, just a query template        | Yes, loops/conditionals/variables|
| Survives disconnect?      | No                               | Yes                              |
| Visible to other connections? | No                           | Yes                              |
| ORMs create them?         | Yes, automatically               | No, you define these yourself    |

## Prepared Statements and Proxies

Prepared statements are stateful -- the plan lives on a specific DB connection.
This creates a problem with connection pooling:

```
App:  PREPARE get_user ...     →  Proxy  →  Connection A  (plan cached here)
App:  EXECUTE get_user(42)     →  Proxy  →  Connection B  (plan doesn't exist!)
```

If the proxy gives a different backend connection, the EXECUTE fails.

**PgBouncer (transaction mode)**: historically broke prepared statements. Recent
versions track them and re-prepare transparently on new connections.

**PgBouncer (session mode)**: no problem (same connection throughout), but you
lose most pooling benefit.

**ProxySQL**: tracks prepared statements and re-prepares on the backend when
connections switch.

This is one of the trickiest parts of building a database proxy.

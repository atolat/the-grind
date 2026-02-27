# Condition Variables and Wait/Notify

Key concepts:

- Busy waiting (while loop checking state) wastes CPU
- `threading.Condition` lets a thread sleep until notified (zero CPU)
- `condition.wait()` = release lock + sleep (atomic)
- `condition.notify()` = wake up one sleeping thread
- ALWAYS use `while` (not `if`) around `wait()` -- spurious wakeups

See [02-condition-variables.py](https://github.com/atolat/the-grind/blob/main/python-deep-dive/02-condition-variables.py) for runnable code.

## Connection to System Design

This is how connection pools work internally:

- Thread requests a connection, pool is empty → sleep via `wait()`
- Another thread returns a connection → `notify()` wakes up the waiter
- `pool_timeout=30` in SQLAlchemy = wait with a 30-second timeout

## Simple Connection Pool

```python
class SimpleConnectionPool:
    def __init__(self, size):
        self.pool = [f"conn_{i}" for i in range(size)]
        self.condition = threading.Condition()

    def borrow(self, timeout=None):
        with self.condition:
            while len(self.pool) == 0:       # while, not if!
                self.condition.wait(timeout=timeout)
            return self.pool.pop()

    def return_conn(self, conn):
        with self.condition:
            self.pool.append(conn)
            self.condition.notify()          # wake up ONE waiting thread
```

# Threads, Locks, and Race Conditions

Key concepts:

- Threads share memory within a process (unlike processes which are isolated)
- Shared state + multiple threads = race conditions
- Locks (`threading.Lock`) control access to shared state
- `with lock:` is a context manager that auto acquires/releases
- Minimize the critical section (locked code) -- keep it fast

<small>[Run this code locally](https://github.com/atolat/the-grind/blob/main/python-deep-dive/01-threads-and-locks.py) or try snippets in the [Playground](../playground.md).</small>

## Race Condition

`counter += 1` is NOT atomic. It's actually: read → add → write.
Two threads can read the same value, both add 1, both write back = lost update.

```mermaid
sequenceDiagram
    participant T1 as Thread 1
    participant C as counter (shared)
    participant T2 as Thread 2

    Note over C: counter = 0
    T1->>C: READ counter (gets 0)
    T2->>C: READ counter (gets 0)
    T1->>C: WRITE counter = 0 + 1
    Note over C: counter = 1
    T2->>C: WRITE counter = 0 + 1
    Note over C: counter = 1 (lost update!)
```

```python
import threading

counter = 0

def increment_unsafe():
    global counter
    for _ in range(1_000_000):
        counter += 1  # NOT atomic: read, add, write can be interleaved

t1 = threading.Thread(target=increment_unsafe)
t2 = threading.Thread(target=increment_unsafe)
t1.start()
t2.start()
t1.join()
t2.join()

print(f"Unsafe counter (expect 2,000,000): {counter}")  # will be less!
```

## Fix 1: Use a Lock

```mermaid
stateDiagram-v2
    [*] --> Unlocked
    Unlocked --> Acquired: Thread calls acquire()
    Acquired --> Unlocked: Thread calls release()
    Unlocked --> Acquired: Another thread acquires
    Acquired --> Blocked: Other thread tries acquire()
    Blocked --> Acquired: Lock released, blocked thread wakes up
```

Only one thread can hold the lock at a time. `with lock:` is a context
manager -- it acquires on entry and releases on exit (even if an exception
is thrown).

```python
counter = 0
lock = threading.Lock()

def increment_safe():
    global counter
    for _ in range(1_000_000):
        with lock:         # acquire lock (context manager, auto-releases)
            counter += 1   # only one thread at a time

t1 = threading.Thread(target=increment_safe)
t2 = threading.Thread(target=increment_safe)
t1.start()
t2.start()
t1.join()
t2.join()

print(f"Safe counter (expect 2,000,000): {counter}")  # exactly 2,000,000
```

```mermaid
sequenceDiagram
    participant T1 as Thread 1
    participant L as Lock
    participant C as counter (shared)
    participant T2 as Thread 2

    T1->>L: acquire()
    activate L
    Note over L: LOCKED
    T2->>L: acquire()
    Note over T2: BLOCKED (waiting)
    rect rgb(50, 50, 80)
        Note over T1,C: Critical Section
        T1->>C: READ counter
        T1->>C: WRITE counter + 1
    end
    T1->>L: release()
    deactivate L
    Note over L: UNLOCKED
    L->>T2: acquired!
    activate L
    rect rgb(50, 50, 80)
        Note over T2,C: Critical Section
        T2->>C: READ counter
        T2->>C: WRITE counter + 1
    end
    T2->>L: release()
    deactivate L
```

Downside: if ALL the work is inside the lock, you've made it sequential again.

## Fix 2: Avoid Shared State

Each thread works on its own counter, combine at the end.
Often simpler and less bug-prone than locking.

```python
def increment_isolated(results, index):
    local_counter = 0
    for _ in range(1_000_000):
        local_counter += 1
    results[index] = local_counter

results = [0, 0]
t1 = threading.Thread(target=increment_isolated, args=(results, 0))
t2 = threading.Thread(target=increment_isolated, args=(results, 1))
t1.start()
t2.start()
t1.join()
t2.join()

print(f"Isolated counter (expect 2,000,000): {sum(results)}")
```

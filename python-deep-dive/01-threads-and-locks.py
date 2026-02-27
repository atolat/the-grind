"""
Threads, Locks, and Race Conditions

Key concepts:
- Threads share memory within a process (unlike processes which are isolated)
- Shared state + multiple threads = race conditions
- Locks (threading.Lock) control access to shared state
- "with lock:" is a context manager that auto acquires/releases
- Minimize the critical section (locked code) -- keep it fast
"""

import threading

# =============================================================================
# Race condition: counter += 1 is NOT atomic
# It's actually: read → add → write
# Two threads can read the same value, both add 1, both write back = lost update
# =============================================================================

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


# =============================================================================
# Fix 1: Use a lock
# Only one thread can hold the lock at a time
# Downside: if ALL the work is inside the lock, you've made it sequential again
# =============================================================================

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


# =============================================================================
# Fix 2: Avoid shared state entirely
# Each thread works on its own counter, combine at the end
# Often simpler and less bug-prone than locking
# =============================================================================

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

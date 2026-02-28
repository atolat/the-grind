# Simple Message Queue Implementation

Concepts exercised:

- `threading.Lock`, `threading.Condition` (from 01 and 02)
- Dataclasses
- Ack-based delivery, visibility timeout, redelivery
- Producer/consumer pattern

See [03-simple-message-queue.py](https://github.com/atolat/the-grind/blob/main/python-deep-dive/03-simple-message-queue.py) for runnable code.

## Design

A message queue with ack-based delivery:

1. Producer publishes messages to the queue
2. Consumer receives a message (moved to "in flight", invisible to others)
3. Consumer processes and sends ack (message deleted permanently)
4. If no ack within visibility timeout, message reappears in queue

```mermaid
graph LR
    P1[Producer 1] -->|publish| Q[(Queue)]
    P2[Producer 2] -->|publish| Q
    Q -->|receive| IF{{"In-Flight Map<br/>(msg_id → msg, timestamp)"}}
    IF -->|ack| D["Deleted<br/>(done)"]
    IF -->|"timeout<br/>(no ack)"| Q
    Q -->|receive| C1[Consumer 1]
    Q -->|receive| C2[Consumer 2]
```

```
Borrow: acquire lock → pop from queue → add to in_flight → release lock → process
Ack:    acquire lock → remove from in_flight → release lock
Requeue: acquire lock → check timestamps → move expired back to queue → notify → release lock
```

```mermaid
stateDiagram-v2
    [*] --> Queued: producer publishes
    Queued --> InFlight: consumer calls receive()
    InFlight --> Acked: consumer calls ack()
    InFlight --> Queued: visibility timeout expires (no ack)
    Acked --> [*]: message permanently deleted
```

```mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Queue
    participant IF as In-Flight Map
    participant C as Consumer

    P->>Q: publish(message)
    Q->>Q: notify() waiting consumers

    C->>Q: receive()
    Q->>IF: move message to in-flight
    Q->>C: return message + receipt_id

    Note over C: processing message...

    alt Consumer succeeds
        C->>IF: ack(receipt_id)
        IF->>IF: delete message
        Note over IF: message permanently gone
    else Visibility timeout expires
        Note over IF: timeout reached, no ack
        IF->>Q: requeue message
        Q->>Q: notify() waiting consumers
        Note over Q: message available again
    end
```

## Key Decisions

- **Single lock** for both queue and in_flight dict, because operations cross both
  (receive reads queue + writes dict, requeue reads dict + writes queue)
- **`wait_for`** instead of manual `wait()` + check loop -- handles spurious wakeups cleanly
- **Dict for in_flight** -- maps message ID → (message, timestamp) for timeout checking

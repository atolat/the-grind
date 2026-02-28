# Kafka Architecture

## Core Concept: The Append-Only Log

Everything in Kafka is built on one idea: an append-only log. You never delete,
never update. Only append. Consumers move their pointer (offset) forward.

```
Topic: "orders"

offset:  0       1       2       3       4       5
       [order1][order2][order3][order4][order5][order6]
                                  ↑                    ↑
                          Consumer reads here     new writes go here
```

Messages are retained for a configurable period (hours, days, forever),
regardless of whether anyone consumed them.

## Partitions: Scaling the Log

A single log on one machine can't handle 100k messages/second. Kafka splits
topics into **partitions** -- separate append-only logs spread across multiple
machines (brokers).

```
Topic: "orders" (3 partitions)

Broker 1:   Partition 0  [msg0][msg3][msg6][msg9] ...
Broker 2:   Partition 1  [msg1][msg4][msg7][msg10] ...
Broker 3:   Partition 2  [msg2][msg5][msg8][msg11] ...
```

```mermaid
graph TD
    T["Topic: orders"] --> P0["Partition 0 (Broker 1)"]
    T --> P1["Partition 1 (Broker 2)"]
    T --> P2["Partition 2 (Broker 3)"]
    P0 --- M00["msg0"] --- M03["msg3"] --- M06["msg6"] --- M09["msg9"]
    P1 --- M01["msg1"] --- M04["msg4"] --- M07["msg7"] --- M10["msg10"]
    P2 --- M02["msg2"] --- M05["msg5"] --- M08["msg8"] --- M11["msg11"]
```

### Partition Assignment

Producers decide which partition a message goes to:

```
partition = hash(message_key) % num_partitions
```

Example: hash("customer_123") % 3 = 2, so all orders for customer_123
land in Partition 2.

```mermaid
flowchart LR
    P[Producer] --> H{"hash(key) % 3"}
    H -->|"hash = 0"| P0[Partition 0]
    H -->|"hash = 1"| P1[Partition 1]
    H -->|"hash = 2"| P2[Partition 2]

    K1["key: customer_100"] -.->|"hash % 3 = 1"| P1
    K2["key: customer_123"] -.->|"hash % 3 = 2"| P2
    K3["key: customer_456"] -.->|"hash % 3 = 0"| P0
```

### Why Key-Based Partitioning?

**Ordering is guaranteed within a partition, NOT across partitions.**

```
Key-based (customer_123 always → Partition 2):
  create → pay → ship → deliver  (all in Partition 2, ordered) ✓

Round-robin (customer_123 scattered):
  create → Partition 0
  pay    → Partition 1
  ship   → Partition 2
  deliver→ Partition 0
  Consumer might process: pay → create → ship → deliver  ✗
```

If ordering doesn't matter (logs, metrics), round-robin is fine and gives
better load distribution.

### Partition Count = Max Parallelism

The number of partitions sets the upper limit on consumer parallelism within
a consumer group. 3 partitions = at most 3 active consumers.
- 4 consumers with 3 partitions → 1 consumer sits idle (standby)
- Choose partition count carefully: too few = can't scale, too many = overhead

## Consumer Groups

Multiple consumers form a **consumer group**. Kafka assigns each partition to
exactly one consumer in the group.

```
Consumer Group: "order-service"

Consumer A (machine 1)  ←──  Partition 0
Consumer B (machine 2)  ←──  Partition 1
Consumer C (machine 3)  ←──  Partition 2
```

```mermaid
graph LR
    subgraph Topic["Topic: orders"]
        P0[Partition 0]
        P1[Partition 1]
        P2[Partition 2]
    end

    subgraph CG["Consumer Group: order-service"]
        CA[Consumer A]
        CB[Consumer B]
        CC[Consumer C]
    end

    P0 --> CA
    P1 --> CB
    P2 --> CC
```

### All Consumers in a Group Run the Same Code

Each consumer is a separate process, typically on a separate machine/container.
Same code, different instances. Scale by adding more processes.

```
Machine 1: python order_service.py   →  Consumer A (reads Partition 0)
Machine 2: python order_service.py   →  Consumer B (reads Partition 1)
Machine 3: python order_service.py   →  Consumer C (reads Partition 2)
```

### Different Groups = Different Services

Different consumer groups read the same topic independently, each maintaining
their own offsets.

```
Group "order-service":   processes orders    (3 instances)
Group "analytics":       aggregates metrics  (1 instance)
Group "email-service":   sends notifications (2 instances)

All read the same "orders" topic. No fan-out configuration needed.
```

```mermaid
graph LR
    subgraph Topic["Topic: orders (3 partitions)"]
        P0[P0]
        P1[P1]
        P2[P2]
    end

    subgraph G1["Group: order-service"]
        A1[Consumer A]
        B1[Consumer B]
        C1[Consumer C]
    end

    subgraph G2["Group: analytics"]
        X1["Consumer X (reads all)"]
    end

    subgraph G3["Group: email-service"]
        E1[Consumer E]
        F1[Consumer F]
    end

    P0 --> A1
    P1 --> B1
    P2 --> C1

    P0 --> X1
    P1 --> X1
    P2 --> X1

    P0 --> E1
    P1 --> E1
    P2 --> F1
```

### Rebalancing

If a consumer dies (detected via heartbeat timeout), Kafka redistributes
its partition to a surviving consumer:

```
Before:
  Consumer A ← Partition 0
  Consumer B ← Partition 1    ← dies
  Consumer C ← Partition 2

After rebalance:
  Consumer A ← Partition 0, Partition 1   ← picks up B's work
  Consumer C ← Partition 2
```

```mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka Broker
    participant OS as __consumer_offsets

    C->>K: poll() from partition 0
    K->>C: messages at offsets 5, 6, 7
    C->>C: process messages
    C->>OS: commit offset 8 (next to read)
    Note over OS: stores (group, partition 0) = 8
    C->>K: poll() from partition 0
    K->>C: messages starting at offset 8
```

### Threading Model

The Kafka consumer client is NOT thread-safe. Typical patterns:

```
Recommended (simple):
  1 process = 1 consumer = 1 thread polling
  Scale by running more processes (Kubernetes replicas)

Alternative (when processing is slow):
  1 process = 1 consumer polling → dispatches to thread pool
  Polling thread fetches, worker threads process
  Tradeoff: more throughput, but ack/offset management gets complex
```

## Replication

Each partition has a leader and replicas across brokers (same as DB
primary/replica concept):

```
Broker 1:  Partition 0 (leader)   | Partition 2 (replica)
Broker 2:  Partition 1 (leader)   | Partition 0 (replica)
Broker 3:  Partition 2 (leader)   | Partition 1 (replica)
```

- Producers write to the leader
- Replicas are for fault tolerance
- If a broker dies, a replica is promoted to leader

```mermaid
graph TD
    subgraph B1["Broker 1"]
        P0L["P0 (leader)"]
        P2R["P2 (replica)"]
    end

    subgraph B2["Broker 2"]
        P1L["P1 (leader)"]
        P0R["P0 (replica)"]
    end

    subgraph B3["Broker 3"]
        P2L["P2 (leader)"]
        P1R["P1 (replica)"]
    end

    P0L -- "replicates to" --> P0R
    P1L -- "replicates to" --> P1R
    P2L -- "replicates to" --> P2R

    Producer --> P0L
    Producer --> P1L
    Producer --> P2L
```

## Full Architecture

```
Producers                    Kafka Cluster                     Consumer Groups

                    ┌────────────────────────────┐
                    │  Broker 1                  │
 Producer A ──────→ │    Partition 0 (leader)     │ ──→  Group "order-service"
                    │    Partition 2 (replica)    │        Consumer A ← P0
                    ├────────────────────────────┤        Consumer B ← P1
                    │  Broker 2                  │        Consumer C ← P2
 Producer B ──────→ │    Partition 1 (leader)     │
                    │    Partition 0 (replica)    │     Group "analytics"
                    ├────────────────────────────┤        Consumer X ← P0,P1,P2
                    │  Broker 3                  │
                    │    Partition 2 (leader)     │
                    │    Partition 1 (replica)    │
                    └────────────────────────────┘
```

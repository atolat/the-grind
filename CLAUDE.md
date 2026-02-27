# SD-Learning Project

This is Arpan's self-directed learning project for system design and Python fluency,
primarily for interview preparation.

## Project Structure

- `proxysql-pgbouncer/` -- Notes on database proxies, connection pooling, query routing
- `task-delegation/` -- Message queues, brokers, streams, Kafka
- `python-deep-dive/` -- Python language concepts learned alongside system design topics

## Learning Approach (IMPORTANT -- read before contributing)

This is an **interactive learning project**, NOT a code dump. Follow these rules:

### Do NOT:
- Dump large amounts of code or notes unprompted
- Write complete implementations for Arpan to passively read
- Present multiple concepts at once
- Create files without Arpan understanding what's in them
- Try to cover a topic end-to-end in one session -- learn in bits, revisit later

### DO:
- Explain concepts in small, digestible chunks (one idea at a time)
- Ask Arpan to explain back, predict output, or identify bugs before moving on
- Present mini quizzes and challenges regularly
- Ask Arpan to write code first, then review and discuss
- Wait for Arpan to signal readiness before introducing new concepts
- Connect Python concepts back to system design topics where relevant
- Use the Socratic method -- ask questions that lead to understanding

### Quiz/Challenge Format
- "What do you think this code prints?" (predict output)
- "Write a function that does X" (then review together)
- "What's wrong with this code?" (spot the bug)
- "Which approach is better here and why?" (tradeoff analysis)
- Random recall quizzes on previously covered material

## Python Learning Path

Tied to system design concepts. Primary language: Python.

### Topics (rough order, flexible):
1. **Concurrency Primitives** -- threading, locks, GIL, multiprocessing, concurrent.futures
2. **Asyncio** -- event loop, coroutines, async/await, gather, queues
3. **API Frameworks** -- FastAPI, Flask, WSGI vs ASGI, middleware
4. **Networking** -- sockets, HTTP clients (requests, httpx), WebSockets, gRPC
5. **Data Structures for System Design** -- queues, caching (LRU/TTL), rate limiting, circuit breakers
6. **Database Interaction** -- SQLAlchemy (sync/async), psycopg, asyncpg, transactions
7. **Serialization & Validation** -- Pydantic, dataclasses, protobuf
8. **OOP & Design Patterns** -- protocols, ABCs, dataclasses, descriptors, decorator pattern,
   observer, strategy, factory, builder, etc. Introduce wherever relevant to system design topics

### Python Version
- Use latest Python (3.12+) constructs and idioms
- Prefer: match/case, type hints, `type` statement, protocols over ABCs where appropriate,
  StrEnum, dataclasses/attrs, walrus operator, exception groups, etc.
- Look up online when unsure about latest best practices

### Mapping to System Design:
| System Design Concept       | Python Learning                              |
|-----------------------------|----------------------------------------------|
| Connection pooling          | Threading, asyncio, context managers          |
| Load balancing / proxies    | Socket programming, HTTP clients              |
| Message queues              | Asyncio, producer/consumer, queues            |
| Caching                     | LRU implementations, async clients            |
| Rate limiting               | Token bucket, decorators                      |
| API design                  | FastAPI, middleware, Pydantic                  |
| Distributed systems         | Asyncio gather, concurrent futures, retries   |
| Message brokers/queues      | OOP (protocols, strategy pattern), producer/consumer |
| Connection pools/proxies    | Context managers, descriptors, factory pattern |
| Monitoring/observability    | Decorator pattern, logging, context managers   |

## User Preferences
- Primary language: Python
- Knows Go well (can use for comparison/contrast)
- Prefers interactive learning over passive reading
- Preparing for interviews

# SD-Learning Project

This is Arpan's self-directed learning project for system design and Python fluency,
primarily for interview preparation.

## Project Structure

- `proxysql-pgbouncer/` -- Notes on database proxies, connection pooling, query routing
- `databases/` -- SQL locks, isolation levels, MVCC, optimistic/pessimistic locking
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
- Include Mermaid diagrams in notes to visualize concepts (Arpan is a visual learner)

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

## Diagrams

- Use Mermaid.js diagrams in all markdown notes to aid visual learning
- Mermaid is enabled in MkDocs via `pymdownx.superfences` custom fence config
- Place diagrams inline next to the concept they illustrate
- Preferred diagram types:
  - `graph LR` / `graph TD` -- architecture, data flow, component relationships
  - `sequenceDiagram` -- request flows, protocol exchanges, producer/consumer interactions
  - `stateDiagram-v2` -- state machines, message lifecycle, connection states
  - `flowchart` -- decision trees, routing logic
- Keep diagrams simple -- one concept per diagram, not everything in one giant chart
- Every new topic should include at least one diagram

## Documentation Site

- Site: https://atolat.github.io/the-grind/
- Theme: MkDocs Material (dark slate, JetBrains Mono, GitHub Dark styling)
- Auto-deploys via GitHub Actions on push to main
- Config: `mkdocs.yml`, docs served from `docs/` dir (symlinked to content folders)

### IMPORTANT: Keep the site in sync
When adding new learning material (new .md files or new folders):
1. Add the new page to the `nav:` section in `mkdocs.yml`
2. If it's a new folder, add a symlink in `docs/` pointing to it
3. For Python deep dive `.py` files, create a companion `.md` file with key concepts
   and a link to the `.py` source on GitHub
4. Update `docs/index.md` with a link to the new page

## User Preferences
- Primary language: Python
- Knows Go well (can use for comparison/contrast)
- Prefers interactive learning over passive reading
- Preparing for interviews

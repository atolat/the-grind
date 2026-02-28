"""
Kafka Demo Orchestrator

Demonstrates two core Kafka concepts:

Demo 1 - Single consumer group with multiple consumers:
  Two consumers share the same group_id. Kafka assigns partitions to each,
  so messages are split between them. Each message is consumed by exactly
  one consumer. This is how you scale processing horizontally.

Demo 2 - Multiple consumer groups:
  Two consumers with different group_ids. Each group independently reads
  ALL messages from the topic. This is how different services (order processing,
  analytics, email) can each consume the same event stream.

Prerequisites:
  - Kafka running: docker compose up -d  (from this directory)
  - pip install kafka-python-ng

Docs:
- Consumer groups: https://kafka.apache.org/documentation/#intro_consumers
- KafkaAdminClient: https://kafka-python.readthedocs.io/en/master/apidoc/KafkaAdminClient.html
- threading.Event: https://docs.python.org/3/library/threading.html#event-objects

Run: python run_demo.py
"""

import threading
import time
import uuid
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError


BOOTSTRAP = ["localhost:9092"]


def create_topic(name: str, partitions: int = 3) -> str:
    """Create a fresh topic so offsets start clean.

    Each demo uses a unique topic name (with a random suffix) to avoid
    interference from previous runs. In production, topics are created
    once and reused -- you don't create new ones per run.

    replication_factor=1 because we only have one broker in our Docker setup.
    In production, this would be 2 or 3 for fault tolerance.
    """
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    try:
        admin.create_topics([
            NewTopic(name=name, num_partitions=partitions, replication_factor=1)
        ])
        print(f"Created topic '{name}' with {partitions} partitions")
    except TopicAlreadyExistsError:
        pass
    admin.close()
    return name


def produce_orders(topic: str):
    """Send 6 test orders to the given topic.

    Orders are keyed by customer_id so all orders for the same customer
    land in the same partition (preserving per-customer ordering).
    """
    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        key_serializer=lambda x: x.encode("utf-8"),
        value_serializer=lambda x: x.encode("utf-8"),
    )

    orders = [
        ("customer_1", "Laptop"),
        ("customer_2", "Mouse"),
        ("customer_1", "Charger"),
        ("customer_3", "Keyboard"),
        ("customer_2", "Monitor"),
        ("customer_1", "USB Cable"),
    ]

    print("--- PRODUCING ---")
    for customer_id, item in orders:
        producer.send(topic, key=customer_id, value=item)
        print(f"  Sent: key={customer_id} value={item}")

    producer.flush()  # block until all messages are delivered
    producer.close()
    print()


def run_consumer(
    name: str,
    group_id: str,
    topic: str,
    stop_event: threading.Event,
    results: list,
):
    """Consumer loop that runs in a background thread until stop_event is set.

    Args:
        name: human-readable name for logging (e.g., "consumer-A")
        group_id: Kafka consumer group. Consumers with the same group_id
            share partitions. Different group_ids consume independently.
        topic: Kafka topic to consume from.
        stop_event: threading.Event used to signal this thread to shut down.
            The main thread calls stop_event.set() when it's time to stop.
        results: shared list to collect consumed messages (for assertions/counting).

    consumer_timeout_ms: how long to wait for new messages before the iterator
    returns (breaks out of the for loop). Without this, the for loop blocks
    indefinitely. We set it to 2000ms so the outer while loop can check
    stop_event periodically.
    """
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=BOOTSTRAP,
        group_id=group_id,
        auto_offset_reset="earliest",  # start from beginning of topic
        key_deserializer=lambda x: x.decode("utf-8"),
        value_deserializer=lambda x: x.decode("utf-8"),
        consumer_timeout_ms=2000,  # yield control after 2s of no messages
    )

    # Outer loop: keep consuming until stop_event is set by the main thread.
    # Inner loop (for message in consumer): iterates over messages, yielding
    # each one. Breaks after consumer_timeout_ms of inactivity.
    while not stop_event.is_set():
        for message in consumer:
            line = (
                f"  [{name} | group={group_id}] "
                f"partition={message.partition} offset={message.offset} "
                f"key={message.key} value={message.value}"
            )
            print(line)
            results.append(line)
            if stop_event.is_set():
                break

    consumer.close()


def demo_single_group():
    """Demo 1: Two consumers in the SAME group -- partitions are split.

    With 3 partitions and 2 consumers in one group, Kafka assigns:
      - consumer-A gets some partitions (e.g., partition 0, 2)
      - consumer-B gets the rest (e.g., partition 1)

    Each message is delivered to exactly ONE consumer. This is how you
    horizontally scale processing -- add more consumers (up to the number
    of partitions) to increase throughput.
    """
    print("=" * 60)
    print("DEMO 1: Two consumers in ONE group (partition splitting)")
    print("=" * 60)

    topic = create_topic(f"demo1-{uuid.uuid4().hex[:6]}")
    produce_orders(topic)
    time.sleep(1)  # give Kafka a moment to commit the messages

    # threading.Event is a simple flag: .set() turns it on, .is_set() checks it.
    # Used here to signal consumer threads to shut down gracefully.
    # See: https://docs.python.org/3/library/threading.html#event-objects
    stop = threading.Event()
    results = []

    # Both consumers use group_id="group-1", so they share partitions
    t1 = threading.Thread(target=run_consumer, args=("consumer-A", "group-1", topic, stop, results))
    t2 = threading.Thread(target=run_consumer, args=("consumer-B", "group-1", topic, stop, results))

    print("--- CONSUMING (same group) ---")
    t1.start()
    t2.start()

    # Wait long enough for consumers to join the group, rebalance, and consume
    time.sleep(10)
    stop.set()   # signal consumers to stop
    t1.join()    # wait for consumer threads to finish
    t2.join()

    print(f"\nTotal messages consumed: {len(results)}")
    print("Note: each message was consumed by ONLY ONE consumer in the group.\n")


def demo_multiple_groups():
    """Demo 2: Two consumers in DIFFERENT groups -- both see ALL messages.

    Different group_ids = independent consumption. Each group maintains its
    own offsets. This is the stream advantage over queues -- no need to
    configure fan-out or duplicate queues. Just point a new service at
    the same topic with a new group_id.
    """
    print("=" * 60)
    print("DEMO 2: Two consumers in DIFFERENT groups (independent)")
    print("=" * 60)

    topic = create_topic(f"demo2-{uuid.uuid4().hex[:6]}")
    produce_orders(topic)
    time.sleep(1)

    stop = threading.Event()
    results_a = []
    results_b = []

    # Different group_ids: "analytics" and "email-service"
    # Each will consume ALL 6 messages independently
    t1 = threading.Thread(target=run_consumer, args=("consumer-X", "analytics", topic, stop, results_a))
    t2 = threading.Thread(target=run_consumer, args=("consumer-Y", "email-service", topic, stop, results_b))

    print("--- CONSUMING (different groups) ---")
    t1.start()
    t2.start()

    time.sleep(10)
    stop.set()
    t1.join()
    t2.join()

    print(f"\nGroup 'analytics' consumed:     {len(results_a)} messages")
    print(f"Group 'email-service' consumed:  {len(results_b)} messages")
    print("Note: BOTH groups consumed ALL messages independently.\n")


if __name__ == "__main__":
    demo_single_group()
    demo_multiple_groups()
    print("Done! Stop Kafka with: docker compose down")

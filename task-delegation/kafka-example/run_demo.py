"""
Kafka Demo Orchestrator

Demonstrates:
1. Single consumer group with multiple consumers (partition splitting)
2. Multiple consumer groups (independent consumption of same messages)
3. Key-based partition routing

Prerequisites:
  - Kafka running: docker compose up -d
  - pip install kafka-python-ng

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
    """Create a fresh topic so offsets start clean. Returns topic name."""
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    try:
        admin.create_topics([NewTopic(name=name, num_partitions=partitions, replication_factor=1)])
        print(f"Created topic '{name}' with {partitions} partitions")
    except TopicAlreadyExistsError:
        pass
    admin.close()
    return name


def produce_orders(topic: str):
    """Send test orders to the given topic."""
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

    producer.flush()
    producer.close()
    print()


def run_consumer(name: str, group_id: str, topic: str, stop_event: threading.Event, results: list):
    """Consumer loop that runs until stop_event is set."""
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=BOOTSTRAP,
        group_id=group_id,
        auto_offset_reset="earliest",
        key_deserializer=lambda x: x.decode("utf-8"),
        value_deserializer=lambda x: x.decode("utf-8"),
        consumer_timeout_ms=2000,
    )

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
    """Two consumers in the SAME group -- partitions are split between them."""
    print("=" * 60)
    print("DEMO 1: Two consumers in ONE group (partition splitting)")
    print("=" * 60)

    topic = create_topic(f"demo1-{uuid.uuid4().hex[:6]}")
    produce_orders(topic)
    time.sleep(1)

    stop = threading.Event()
    results = []

    t1 = threading.Thread(target=run_consumer, args=("consumer-A", "group-1", topic, stop, results))
    t2 = threading.Thread(target=run_consumer, args=("consumer-B", "group-1", topic, stop, results))

    print("--- CONSUMING (same group) ---")
    t1.start()
    t2.start()

    time.sleep(10)
    stop.set()
    t1.join()
    t2.join()

    print(f"\nTotal messages consumed: {len(results)}")
    print("Note: each message was consumed by ONLY ONE consumer in the group.\n")


def demo_multiple_groups():
    """Two consumers in DIFFERENT groups -- both see ALL messages."""
    print("=" * 60)
    print("DEMO 2: Two consumers in DIFFERENT groups (independent)")
    print("=" * 60)

    topic = create_topic(f"demo2-{uuid.uuid4().hex[:6]}")
    produce_orders(topic)
    time.sleep(1)

    stop = threading.Event()
    results_a = []
    results_b = []

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

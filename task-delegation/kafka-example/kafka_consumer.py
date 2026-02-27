"""
Kafka Consumer

Reads messages from the "orders" topic.
Part of the "order-service" consumer group.

Run: python kafka_consumer.py
(Run multiple instances to see partition assignment / rebalancing)
"""

from kafka import KafkaConsumer
import json


def create_consumer(group_id: str = "order-service") -> KafkaConsumer:
    """Create and return a KafkaConsumer that deserializes JSON values."""
    ...


if __name__ == "__main__":
    consumer = create_consumer()
    print("Waiting for messages... (Ctrl+C to stop)")

    try:
        for message in consumer:
            # message has: .topic, .partition, .offset, .key, .value
            # Print all of these so you can see partition assignment
            print(
                f"Partition: {message.partition} | "
                f"Offset: {message.offset} | "
                f"Key: {message.key} | "
                f"Value: {message.value}"
            )
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        consumer.close()

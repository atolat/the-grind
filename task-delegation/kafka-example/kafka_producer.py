"""
Kafka Producer

Sends messages to the "orders" topic.
Each message has a customer_id as the key (for partition routing)
and an order description as the value.

Run: python kafka_producer.py
"""

from kafka import KafkaProducer
import json


def create_producer() -> KafkaProducer:
    """Create and return a KafkaProducer that serializes values as JSON."""
    producer = KafkaProducer(
        bootstrap_servers=["localhost:9092"],
        key_serializer=lambda x: x.encode("utf-8"),
        value_serializer=lambda x: x.encode("utf-8")
    )
    return producer


def send_order(producer: KafkaProducer, customer_id: str, description: str):
    """Send an order message to the 'orders' topic with customer_id as key."""
    producer.send("orders", key=customer_id, value=description)


if __name__ == "__main__":
    producer = create_producer()

    # Send some test orders -- same customer should go to same partition
    orders = [
        ("customer_1", "Laptop"),
        ("customer_2", "Mouse"),
        ("customer_1", "Charger"),     # same customer as first order
        ("customer_3", "Keyboard"),
        ("customer_2", "Monitor"),     # same customer as second order
        ("customer_1", "USB Cable"),   # same customer again
    ]

    for customer_id, description in orders:
        send_order(producer, customer_id, description)

    producer.flush()  # wait for all messages to be sent
    producer.close()
    print("All orders sent!")

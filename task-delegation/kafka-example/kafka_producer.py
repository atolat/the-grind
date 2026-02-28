"""
Kafka Producer

Sends messages to the "orders" topic.
Each message has a customer_id as the key (for partition routing)
and an order description as the value.

Key concepts:
- Kafka only deals in bytes -- serializers convert Python objects to bytes
- Keys determine partition assignment: hash(key) % num_partitions
- Same key = same partition = ordering guaranteed for that key
- producer.send() is async (returns a Future), flush() waits for all to complete

Docs:
- kafka-python-ng KafkaProducer: https://kafka-python.readthedocs.io/en/master/apidoc/KafkaProducer.html
- Kafka producer concepts: https://kafka.apache.org/documentation/#producerapi

Run: python kafka_producer.py
"""

from kafka import KafkaProducer


def create_producer() -> KafkaProducer:
    """Create and return a KafkaProducer.

    bootstrap_servers: initial Kafka broker(s) to connect to. The client
    discovers other brokers automatically after connecting.

    key_serializer / value_serializer: functions that convert Python objects
    to bytes. Kafka only transmits raw bytes -- it has no concept of strings,
    dicts, etc. Here we use simple UTF-8 encoding since our keys and values
    are plain strings. For structured data (dicts), you'd use json.dumps().encode()
    or protobuf/avro serialization.
    """
    producer = KafkaProducer(
        bootstrap_servers=["localhost:9092"],
        key_serializer=lambda x: x.encode("utf-8"),
        value_serializer=lambda x: x.encode("utf-8"),
    )
    return producer


def send_order(producer: KafkaProducer, customer_id: str, description: str):
    """Send an order message to the 'orders' topic with customer_id as key.

    The key determines which partition this message lands in:
      partition = hash(customer_id) % num_partitions

    So all orders for the same customer go to the same partition,
    guaranteeing ordering per customer.

    send() is asynchronous -- it buffers the message and returns immediately.
    Call producer.flush() to block until all buffered messages are sent.
    """
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

    # flush() blocks until all buffered messages are actually sent to Kafka.
    # Without this, the program might exit before messages are delivered.
    producer.flush()
    producer.close()
    print("All orders sent!")

"""
Kafka Consumer

Reads messages from the "orders" topic.
Part of the "order-service" consumer group.

Key concepts:
- Consumers in the same group split partitions (each message consumed once)
- Consumers in different groups consume independently (each sees all messages)
- auto_offset_reset="earliest" means start from the beginning if no committed offset
- The consumer loop blocks (polls) until new messages arrive
- Offsets are committed (auto or manual) so the consumer can resume after restart

Docs:
- kafka-python-ng KafkaConsumer: https://kafka-python.readthedocs.io/en/master/apidoc/KafkaConsumer.html
- Kafka consumer concepts: https://kafka.apache.org/documentation/#consumerapi
- Consumer groups: https://kafka.apache.org/documentation/#intro_consumers

Run: python kafka_consumer.py
(Run multiple instances to see partition assignment / rebalancing)
"""

from kafka import KafkaConsumer


def create_consumer(group_id: str = "order-service") -> KafkaConsumer:
    """Create and return a KafkaConsumer.

    Args:
        group_id: consumers with the same group_id form a consumer group.
            Kafka assigns each partition to exactly one consumer in the group.
            If a consumer dies, its partitions are reassigned (rebalancing).

    Config:
        "orders": the topic to subscribe to (first positional arg).

        bootstrap_servers: same as producer -- initial broker(s) for discovery.

        auto_offset_reset: what to do when there's no committed offset
        (e.g., first time this group reads the topic).
            "earliest" = start from the beginning (offset 0)
            "latest"   = only read new messages from now on

        key_deserializer / value_deserializer: reverse of producer's serializers.
        Converts bytes back to Python objects.
        Must match the producer's serializers -- if producer encodes as UTF-8,
        consumer must decode as UTF-8.

        enable_auto_commit (default True): automatically commit offsets
        periodically. Simple but if consumer crashes between auto-commits,
        some messages may be reprocessed. For exactly-once semantics,
        set to False and call consumer.commit() manually after processing.
    """
    consumer = KafkaConsumer(
        "orders",
        bootstrap_servers=["localhost:9092"],
        group_id=group_id,
        auto_offset_reset="earliest",
        key_deserializer=lambda x: x.decode("utf-8"),
        value_deserializer=lambda x: x.decode("utf-8"),
    )
    return consumer


if __name__ == "__main__":
    consumer = create_consumer()
    print("Waiting for messages... (Ctrl+C to stop)")

    try:
        # Iterating over the consumer blocks and yields messages as they arrive.
        # Each message object has:
        #   .topic     - topic name
        #   .partition - which partition this message is from
        #   .offset    - position within the partition (sequential, starts at 0)
        #   .key       - the message key (deserialized by key_deserializer)
        #   .value     - the message value (deserialized by value_deserializer)
        #   .timestamp - when the message was produced (milliseconds since epoch)
        for message in consumer:
            print(
                f"Partition: {message.partition} | "
                f"Offset: {message.offset} | "
                f"Key: {message.key} | "
                f"Value: {message.value}"
            )
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # close() commits offsets (if auto-commit) and leaves the consumer group.
        # This triggers a rebalance so other consumers can pick up this one's partitions.
        consumer.close()

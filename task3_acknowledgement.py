from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
    save_trace,
)


def main():
    print("=" * 70)
    print("Topic 16 — Task 3: Acknowledgement")
    print("=" * 70)

    engine = CommunicationEngine(max_steps=20)

    print("\nSUCCESS PATH")
    print("-" * 60)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={
            "action": "lookup",
            "query": "customer_order_status",
        },
    )

    ack = engine.acknowledge(
        message,
        receiver="executor",
    )

    print("Original correlation ID:")
    print(message.correlation_id)

    print("\nAcknowledgement:")
    print(f"kind: {ack.kind}")
    print(f"sender: {ack.sender}")
    print(f"recipient: {ack.recipient}")
    print(f"payload: {ack.payload}")
    print(f"correlation_id: {ack.correlation_id}")

    print(
        "\nCorrelation ID preserved:",
        ack.correlation_id == message.correlation_id,
    )

    print("\nREJECTION PATH")
    print("-" * 60)

    try:
        engine.acknowledge(
            message,
            receiver="executor",
        )
    except CommunicationError as exc:
        print("Rejected duplicate acknowledgement:", exc)
        print(f"failure_type={exc.failure_type.value}")

    print("\nUNKNOWN MESSAGE PATH")
    print("-" * 60)

    unknown_message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={
            "action": "unknown_test",
        },
    )

    del engine.messages[unknown_message.correlation_id]

    try:
        engine.acknowledge(
            unknown_message,
            receiver="executor",
        )
    except CommunicationError as exc:
        print("Rejected acknowledgement for unknown message:", exc)
        print(f"failure_type={exc.failure_type.value}")

    trace_path = save_trace(
        engine,
        "traces/task3_trace.json",
    )

    print("\nTRACE SAVED")
    print(trace_path)


if __name__ == "__main__":
    main()
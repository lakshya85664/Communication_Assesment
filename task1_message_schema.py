from communication import (
    CommunicationEngine,
    CommunicationError,
    MessageKind,
    save_trace,
)


def print_message(message) -> None:
    print(f"kind: {message.kind}")
    print(f"sender: {message.sender}")
    print(f"recipient: {message.recipient}")
    print(f"payload: {message.payload}")
    print(f"correlation_id: {message.correlation_id}")


def main() -> None:
    print("=" * 70)
    print("Topic 16 — Task 1: Message Schema")
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

    print("Created message:")
    print_message(message)

    validated = engine.validate(message)

    print("\nValidation:")
    print("Message schema valid:", validated)
    print(
        "Correlation ID is present:",
        bool(message.correlation_id),
    )

    trace_path = save_trace(
        engine,
        "traces/task1_trace.json",
    )

    print("\nTRACE SAVED")
    print(trace_path)

    print("\nREJECTION PATH")
    print("-" * 60)

    try:
        engine.create_message(
            sender="planner",
            recipient="executor",
            kind="invalid_kind",
            payload={
                "action": "lookup",
            },
        )
    except CommunicationError as exc:
        print(
            "Rejected unsupported message kind:",
            exc,
        )
        print(
            f"failure_type={exc.failure_type.value}"
        )

    print("\nSECRET HYGIENE PATH")
    print("-" * 60)

    try:
        engine.create_message(
            sender="planner",
            recipient="executor",
            kind=MessageKind.TASK.value,
            payload={
                "action": "lookup",
                "api_key": "api_key=super_secret_value",
            },
        )
    except CommunicationError as exc:
        print(
            "Rejected secret-like payload:",
            exc,
        )
        print(
            f"failure_type={exc.failure_type.value}"
        )


if __name__ == "__main__":
    main()
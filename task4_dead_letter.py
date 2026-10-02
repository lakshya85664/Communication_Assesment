from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
    save_trace,
)


def main():
    print("=" * 70)
    print("Topic 16 — Task 4: Dead Letter")
    print("=" * 70)

    engine = CommunicationEngine(max_steps=20)

    print("\nTRANSIENT FAILURE PATH")
    print("-" * 60)

    transient_message = engine.create_message(
        sender="planner",
        recipient="unavailable_worker",
        kind=MessageKind.TASK.value,
        payload={
            "action": "process",
            "item": "order_1001",
        },
    )

    transient_entry = engine.dead_letter(
        transient_message,
        FailureType.TRANSIENT,
        "Temporary worker communication failure.",
    )

    print("Dead-lettered message:")
    print("  correlation_id:", transient_entry.message.correlation_id)
    print("  failure_type:", transient_entry.failure_type)
    print("  reason:", transient_entry.reason)
    print("  retryable:", transient_entry.retryable)

    print("\nPERMANENT FAILURE PATH")
    print("-" * 60)

    permanent_message = engine.create_message(
        sender="planner",
        recipient="invalid_worker",
        kind=MessageKind.TASK.value,
        payload={
            "action": "process",
            "item": "order_1002",
        },
    )

    permanent_entry = engine.dead_letter(
        permanent_message,
        FailureType.VALIDATION,
        "Message failed permanent validation.",
    )

    print("Dead-lettered message:")
    print("  correlation_id:", permanent_entry.message.correlation_id)
    print("  failure_type:", permanent_entry.failure_type)
    print("  retryable:", permanent_entry.retryable)

    print("\nREJECTION PATH")
    print("-" * 60)

    try:
        engine.dead_letter(
            transient_message,
            FailureType.TRANSIENT,
            "Duplicate dead-letter attempt.",
        )
    except CommunicationError as exc:
        print("Rejected duplicate dead-letter:", exc)
        print(f"failure_type={exc.failure_type.value}")

    print("\nRETRIEVAL PATH")
    print("-" * 60)

    retrieved = engine.get_dead_letter(
        transient_message.correlation_id
    )

    print("Retrieved dead-letter:")
    print("  correlation_id:", retrieved.message.correlation_id)
    print("  failure_type:", retrieved.failure_type)
    print("  retryable:", retrieved.retryable)

    trace_path = save_trace(
        engine,
        "traces/task4_trace.json",
    )

    print("\nTRACE SAVED")
    print(trace_path)


if __name__ == "__main__":
    main()
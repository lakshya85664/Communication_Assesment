from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
    save_trace,
)


def executor_handler(message):
    return {
        "recipient": message.recipient,
        "action": message.payload["action"],
        "status": "delivered",
    }


def main():
    print("=" * 70)
    print("Topic 16 — Task 2: Routing")
    print("=" * 70)

    engine = CommunicationEngine(max_steps=20)

    print("\nSUCCESS PATH")
    print("-" * 60)

    engine.register_route("executor", executor_handler)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={
            "action": "lookup",
            "query": "customer_order_status",
        },
    )

    result = engine.route_message(message)

    print("Registered route:")
    print("  executor -> executor_handler")

    print("\nMessage delivered:")
    print(result)

    print("\nREJECTION PATH")
    print("-" * 60)

    unknown_message = engine.create_message(
        sender="planner",
        recipient="unknown_agent",
        kind=MessageKind.TASK.value,
        payload={
            "action": "lookup",
        },
    )

    try:
        engine.route_message(unknown_message)
    except CommunicationError as exc:
        print("Rejected unknown route:", exc)
        print(f"failure_type={exc.failure_type.value}")

    print("\nDUPLICATE ROUTE PATH")
    print("-" * 60)

    try:
        engine.register_route("executor", executor_handler)
    except CommunicationError as exc:
        print("Rejected duplicate route:", exc)
        print(f"failure_type={exc.failure_type.value}")

    trace_path = save_trace(
        engine,
        "traces/task2_trace.json",
    )

    print("\nTRACE SAVED")
    print(trace_path)


if __name__ == "__main__":
    main()
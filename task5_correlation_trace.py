from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
    save_trace,
)


def executor_handler(message):
    return {
        "status": "completed",
        "action": message.payload["action"],
    }


def main():
    print("=" * 70)
    print("Topic 16 — Task 5: Correlation Trace")
    print("=" * 70)

    engine = CommunicationEngine(max_steps=20)

    print("\nSUCCESS PATH")
    print("-" * 60)

    engine.register_route(
        "executor",
        executor_handler,
    )

    task_message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={
            "action": "process_order",
            "order_id": "ORDER-1001",
        },
    )

    task_result = engine.route_message(task_message)

    ack = engine.acknowledge(
        task_message,
        receiver="executor",
    )

    result_message = engine.create_message(
        sender="executor",
        recipient="planner",
        kind=MessageKind.RESULT.value,
        payload=task_result,
        correlation_id=task_message.correlation_id,
    )

    trace = engine.correlation_trace(
        task_message.correlation_id
    )

    print("Correlation ID:")
    print(task_message.correlation_id)

    print("\nRelated messages:")
    for message in trace["messages"]:
        print(
            f"  {message['kind']}: "
            f"{message['sender']} -> {message['recipient']}"
        )

    print("\nEvent count:")
    print(trace["event_count"])

    print("\nCorrelation preserved across messages:")
    print(
        task_message.correlation_id
        == ack.correlation_id
        == result_message.correlation_id
    )

    print("\nRESULT MESSAGE")
    print(result_message)

    print("\nREJECTION PATH")
    print("-" * 60)

    try:
        engine.correlation_trace(
            "00000000-0000-0000-0000-000000000000"
        )
    except CommunicationError as exc:
        print("Rejected unknown correlation ID:", exc)
        print(f"failure_type={exc.failure_type.value}")

    print("\nTRACE SAVED")
    trace_path = save_trace(
        engine,
        "traces/task5_trace.json",
    )
    print(trace_path)


if __name__ == "__main__":
    main()
import json

import pytest

from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
)


def handler(message):
    return {
        "status": "completed",
        "action": message.payload["action"],
    }


def create_task(engine):
    return engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={"action": "process"},
    )


def test_correlation_trace_returns_related_messages():
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    task = create_task(engine)

    engine.route_message(task)

    engine.acknowledge(
        task,
        receiver="executor",
    )

    result = engine.create_message(
        sender="executor",
        recipient="planner",
        kind=MessageKind.RESULT.value,
        payload={"status": "completed"},
        correlation_id=task.correlation_id,
    )

    trace = engine.correlation_trace(
        task.correlation_id
    )

    assert trace["correlation_id"] == task.correlation_id
    assert trace["message_count"] == 2
    assert len(trace["messages"]) == 2
    assert result.correlation_id == task.correlation_id


def test_correlation_trace_contains_operational_events():
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    task = create_task(engine)

    engine.route_message(task)

    engine.acknowledge(
        task,
        receiver="executor",
    )

    trace = engine.correlation_trace(
        task.correlation_id
    )

    events = [
        event["event"]
        for event in trace["events"]
    ]

    assert "message_created" in events
    assert "message_validated" in events
    assert "message_routed" in events
    assert "message_acknowledged" in events


def test_correlation_id_is_shared_across_flow():
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    task = create_task(engine)

    engine.route_message(task)

    ack = engine.acknowledge(
        task,
        receiver="executor",
    )

    result = engine.create_message(
        sender="executor",
        recipient="planner",
        kind="result",
        payload={"status": "completed"},
        correlation_id=task.correlation_id,
    )

    assert task.correlation_id == ack.correlation_id
    assert ack.correlation_id == result.correlation_id


def test_unknown_correlation_id_is_rejected():
    engine = CommunicationEngine()

    with pytest.raises(CommunicationError) as exc_info:
        engine.correlation_trace(
            "00000000-0000-0000-0000-000000000000"
        )

    assert exc_info.value.failure_type == FailureType.CORRELATION_NOT_FOUND


def test_invalid_correlation_id_is_rejected():
    engine = CommunicationEngine()

    with pytest.raises(CommunicationError) as exc_info:
        engine.correlation_trace("not-a-uuid")

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_empty_correlation_id_is_rejected():
    engine = CommunicationEngine()

    with pytest.raises(CommunicationError) as exc_info:
        engine.correlation_trace("")

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_correlation_trace_event_is_recorded():
    engine = CommunicationEngine()

    task = create_task(engine)

    engine.correlation_trace(
        task.correlation_id
    )

    events = [
        event.event
        for event in engine.trace
    ]

    assert "correlation_trace_computed" in events


def test_trace_can_be_saved(tmp_path):
    engine = CommunicationEngine()

    task = create_task(engine)

    engine.correlation_trace(
        task.correlation_id
    )

    trace_path = engine.save_trace(
        tmp_path / "task5_trace.json"
    )

    assert trace_path.exists()

    data = json.loads(
        trace_path.read_text(encoding="utf-8")
    )

    assert data["step_count"] > 0
    assert any(
        event["event"] == "correlation_trace_computed"
        for event in data["events"]
    )


def test_step_limit_applies_to_correlation_trace():
    engine = CommunicationEngine(max_steps=1)

    task = create_task(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.correlation_trace(
            task.correlation_id
        )

    assert exc_info.value.failure_type == FailureType.STEP_LIMIT


def test_correlation_trace_preserves_event_order():
    engine = CommunicationEngine()

    task = create_task(engine)

    trace = engine.correlation_trace(
        task.correlation_id
    )

    event_names = [
        event["event"]
        for event in trace["events"]
    ]

    assert event_names == [
        "message_created"
    ]
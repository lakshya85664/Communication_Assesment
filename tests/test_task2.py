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
        "received": True,
        "action": message.payload["action"],
    }


def test_register_route_and_deliver_message():
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={"action": "lookup"},
    )

    result = engine.route_message(message)

    assert result == {
        "received": True,
        "action": "lookup",
    }


def test_unknown_recipient_is_rejected():
    engine = CommunicationEngine()

    message = engine.create_message(
        sender="planner",
        recipient="missing_agent",
        kind="task",
        payload={"action": "lookup"},
    )

    with pytest.raises(CommunicationError) as exc_info:
        engine.route_message(message)

    assert exc_info.value.failure_type == FailureType.ROUTE_NOT_FOUND


def test_duplicate_route_is_rejected():
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    with pytest.raises(CommunicationError) as exc_info:
        engine.register_route("executor", handler)

    assert exc_info.value.failure_type == FailureType.DUPLICATE_ROUTE


def test_route_handler_must_be_callable():
    engine = CommunicationEngine()

    with pytest.raises(CommunicationError) as exc_info:
        engine.register_route("executor", "not-callable")

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_recipient_must_not_be_empty():
    engine = CommunicationEngine()

    with pytest.raises(CommunicationError) as exc_info:
        engine.register_route("", handler)

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_successful_route_is_recorded():
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    engine.route_message(message)

    events = [event.event for event in engine.trace]

    assert "route_registered" in events
    assert "message_created" in events
    assert "message_validated" in events
    assert "message_routed" in events


def test_unknown_route_is_recorded():
    engine = CommunicationEngine()

    message = engine.create_message(
        sender="planner",
        recipient="missing_agent",
        kind="task",
        payload={"action": "lookup"},
    )

    with pytest.raises(CommunicationError):
        engine.route_message(message)

    events = [event.event for event in engine.trace]

    assert "route_rejected" in events


def test_handler_result_secret_is_rejected():
    engine = CommunicationEngine()

    def secret_handler(message):
        return {
            "token": "token=super_secret_value",
        }

    engine.register_route("executor", secret_handler)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    with pytest.raises(CommunicationError) as exc_info:
        engine.route_message(message)

    assert exc_info.value.failure_type == FailureType.SECRET_DETECTED


def test_trace_can_be_saved(tmp_path):
    engine = CommunicationEngine()

    engine.register_route("executor", handler)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    engine.route_message(message)

    trace_path = engine.save_trace(tmp_path / "task2_trace.json")

    assert trace_path.exists()

    data = json.loads(trace_path.read_text(encoding="utf-8"))

    assert data["step_count"] > 0
    assert len(data["events"]) > 0


def test_step_limit_applies_to_routing():
    engine = CommunicationEngine(max_steps=2)

    engine.register_route("executor", handler)

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    with pytest.raises(CommunicationError) as exc_info:
        engine.route_message(message)

    assert exc_info.value.failure_type == FailureType.STEP_LIMIT
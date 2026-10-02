import json

import pytest

from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
)


def create_task(engine):
    return engine.create_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={"action": "lookup"},
    )


def test_acknowledgement_success():
    engine = CommunicationEngine()

    message = create_task(engine)

    ack = engine.acknowledge(
        message,
        receiver="executor",
    )

    assert ack.kind == "ack"
    assert ack.sender == "executor"
    assert ack.recipient == "planner"
    assert ack.payload["acknowledged"] is True


def test_acknowledgement_preserves_correlation_id():
    engine = CommunicationEngine()

    message = create_task(engine)

    ack = engine.acknowledge(
        message,
        receiver="executor",
    )

    assert ack.correlation_id == message.correlation_id


def test_duplicate_ack_is_rejected():
    engine = CommunicationEngine()

    message = create_task(engine)

    engine.acknowledge(
        message,
        receiver="executor",
    )

    with pytest.raises(CommunicationError) as exc_info:
        engine.acknowledge(
            message,
            receiver="executor",
        )

    assert exc_info.value.failure_type == FailureType.DUPLICATE_ACK


def test_unknown_message_ack_is_rejected():
    engine = CommunicationEngine()

    message = create_task(engine)

    del engine.messages[message.correlation_id]

    with pytest.raises(CommunicationError) as exc_info:
        engine.acknowledge(
            message,
            receiver="executor",
        )

    assert exc_info.value.failure_type == FailureType.MESSAGE_NOT_FOUND


def test_ack_event_is_recorded():
    engine = CommunicationEngine()

    message = create_task(engine)

    engine.acknowledge(
        message,
        receiver="executor",
    )

    events = [event.event for event in engine.trace]

    assert "message_acknowledged" in events


def test_ack_event_uses_original_correlation_id():
    engine = CommunicationEngine()

    message = create_task(engine)

    ack = engine.acknowledge(
        message,
        receiver="executor",
    )

    ack_events = [
        event
        for event in engine.trace
        if event.event == "message_acknowledged"
    ]

    assert len(ack_events) == 1
    assert ack_events[0].correlation_id == message.correlation_id
    assert ack.correlation_id == message.correlation_id


def test_ack_receiver_must_not_be_empty():
    engine = CommunicationEngine()

    message = create_task(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.acknowledge(
            message,
            receiver="",
        )

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_trace_can_be_saved(tmp_path):
    engine = CommunicationEngine()

    message = create_task(engine)

    engine.acknowledge(
        message,
        receiver="executor",
    )

    trace_path = engine.save_trace(
        tmp_path / "task3_trace.json"
    )

    assert trace_path.exists()

    data = json.loads(
        trace_path.read_text(encoding="utf-8")
    )

    assert data["step_count"] > 0
    assert any(
        event["event"] == "message_acknowledged"
        for event in data["events"]
    )


def test_step_limit_applies_to_acknowledgement():
    engine = CommunicationEngine(max_steps=2)

    message = create_task(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.acknowledge(
            message,
            receiver="executor",
        )

    assert exc_info.value.failure_type == FailureType.STEP_LIMIT
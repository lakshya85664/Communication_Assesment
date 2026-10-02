import json

import pytest

from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    MessageKind,
)


def create_message(engine, recipient="worker"):
    return engine.create_message(
        sender="planner",
        recipient=recipient,
        kind=MessageKind.TASK.value,
        payload={"action": "process"},
    )


def test_transient_failure_is_dead_lettered_and_retryable():
    engine = CommunicationEngine()

    message = create_message(engine)

    entry = engine.dead_letter(
        message,
        FailureType.TRANSIENT,
        "Temporary communication failure.",
    )

    assert entry.message == message
    assert entry.failure_type == "transient"
    assert entry.retryable is True


def test_permanent_failure_is_not_retryable():
    engine = CommunicationEngine()

    message = create_message(engine)

    entry = engine.dead_letter(
        message,
        FailureType.VALIDATION,
        "Permanent validation failure.",
    )

    assert entry.failure_type == "validation"
    assert entry.retryable is False


def test_dead_letter_can_be_retrieved():
    engine = CommunicationEngine()

    message = create_message(engine)

    engine.dead_letter(
        message,
        FailureType.TRANSIENT,
        "Temporary failure.",
    )

    entry = engine.get_dead_letter(
        message.correlation_id
    )

    assert entry.message.correlation_id == message.correlation_id


def test_duplicate_dead_letter_is_rejected():
    engine = CommunicationEngine()

    message = create_message(engine)

    engine.dead_letter(
        message,
        FailureType.TRANSIENT,
        "Temporary failure.",
    )

    with pytest.raises(CommunicationError) as exc_info:
        engine.dead_letter(
            message,
            FailureType.TRANSIENT,
            "Second attempt.",
        )

    assert exc_info.value.failure_type == FailureType.DEAD_LETTER_DUPLICATE


def test_missing_dead_letter_is_rejected():
    engine = CommunicationEngine()

    message = create_message(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.get_dead_letter(
            message.correlation_id
        )

    assert exc_info.value.failure_type == FailureType.MESSAGE_NOT_FOUND


def test_empty_failure_type_is_rejected():
    engine = CommunicationEngine()

    message = create_message(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.dead_letter(
            message,
            "",
            "Failure reason.",
        )

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_empty_reason_is_rejected():
    engine = CommunicationEngine()

    message = create_message(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.dead_letter(
            message,
            FailureType.TRANSIENT,
            "",
        )

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_secret_in_reason_is_rejected():
    engine = CommunicationEngine()

    message = create_message(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.dead_letter(
            message,
            FailureType.TRANSIENT,
            "token=super_secret_value",
        )

    assert exc_info.value.failure_type == FailureType.SECRET_DETECTED


def test_dead_letter_events_are_recorded():
    engine = CommunicationEngine()

    message = create_message(engine)

    engine.dead_letter(
        message,
        FailureType.TRANSIENT,
        "Temporary failure.",
    )

    engine.get_dead_letter(
        message.correlation_id
    )

    events = [event.event for event in engine.trace]

    assert "message_dead_lettered" in events
    assert "dead_letter_retrieved" in events


def test_dead_letter_preserves_correlation_id():
    engine = CommunicationEngine()

    message = create_message(engine)

    entry = engine.dead_letter(
        message,
        FailureType.TRANSIENT,
        "Temporary failure.",
    )

    assert entry.message.correlation_id == message.correlation_id


def test_trace_can_be_saved(tmp_path):
    engine = CommunicationEngine()

    message = create_message(engine)

    engine.dead_letter(
        message,
        FailureType.TRANSIENT,
        "Temporary failure.",
    )

    trace_path = engine.save_trace(
        tmp_path / "task4_trace.json"
    )

    assert trace_path.exists()

    data = json.loads(
        trace_path.read_text(encoding="utf-8")
    )

    assert data["step_count"] > 0
    assert any(
        event["event"] == "message_dead_lettered"
        for event in data["events"]
    )


def test_step_limit_applies_to_dead_letter():
    engine = CommunicationEngine(max_steps=2)

    message = create_message(engine)

    with pytest.raises(CommunicationError) as exc_info:
        engine.dead_letter(
            message,
            FailureType.TRANSIENT,
            "Temporary failure.",
        )

    assert exc_info.value.failure_type == FailureType.STEP_LIMIT
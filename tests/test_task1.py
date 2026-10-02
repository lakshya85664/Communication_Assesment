import json

import pytest

from communication import (
    CommunicationEngine,
    CommunicationError,
    FailureType,
    Message,
    MessageKind,
    make_message,
    message_to_dict,
)


def test_make_task_message_success():
    message = make_message(
        sender="planner",
        recipient="executor",
        kind=MessageKind.TASK.value,
        payload={"action": "lookup"},
    )

    assert isinstance(message, Message)
    assert message.kind == "task"
    assert message.sender == "planner"
    assert message.recipient == "executor"
    assert message.payload == {"action": "lookup"}
    assert message.correlation_id


def test_result_message_success():
    message = make_message(
        sender="executor",
        recipient="planner",
        kind=MessageKind.RESULT.value,
        payload={"status": "success"},
    )

    assert message.kind == "result"


def test_ack_message_success():
    message = make_message(
        sender="executor",
        recipient="planner",
        kind=MessageKind.ACK.value,
        payload={"received": True},
    )

    assert message.kind == "ack"


def test_unsupported_message_kind_is_rejected():
    with pytest.raises(CommunicationError) as exc_info:
        make_message(
            sender="planner",
            recipient="executor",
            kind="invalid",
            payload={"action": "lookup"},
        )

    assert exc_info.value.failure_type == FailureType.UNSUPPORTED_KIND


def test_payload_must_be_dict():
    with pytest.raises(CommunicationError) as exc_info:
        make_message(
            sender="planner",
            recipient="executor",
            kind="task",
            payload="not-a-dict",
        )

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_sender_must_not_be_empty():
    with pytest.raises(CommunicationError) as exc_info:
        make_message(
            sender="",
            recipient="executor",
            kind="task",
            payload={},
        )

    assert exc_info.value.failure_type == FailureType.VALIDATION


def test_correlation_id_is_uuid():
    message = make_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={},
    )

    assert len(message.correlation_id) == 36
    assert message.correlation_id.count("-") == 4


def test_secret_like_payload_is_rejected():
    with pytest.raises(CommunicationError) as exc_info:
        make_message(
            sender="planner",
            recipient="executor",
            kind="task",
            payload={
                "api_key": "api_key=super_secret_value",
            },
        )

    assert exc_info.value.failure_type == FailureType.SECRET_DETECTED


def test_message_to_dict_contains_contract_fields():
    message = make_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    data = message_to_dict(message)

    assert set(data.keys()) == {
        "kind",
        "sender",
        "recipient",
        "payload",
        "correlation_id",
    }


def test_engine_records_message_events():
    engine = CommunicationEngine()

    message = engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    engine.validate(message)

    assert engine.step_count == 2
    assert len(engine.trace) == 2
    assert engine.trace[0].event == "message_created"
    assert engine.trace[1].event == "message_validated"


def test_trace_can_be_saved(tmp_path):
    engine = CommunicationEngine()

    engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    trace_path = engine.save_trace(tmp_path / "task1_trace.json")

    assert trace_path.exists()

    data = json.loads(trace_path.read_text(encoding="utf-8"))

    assert data["step_count"] == 1
    assert data["max_steps"] == 20
    assert len(data["events"]) == 1


def test_step_limit_is_enforced():
    engine = CommunicationEngine(max_steps=1)

    engine.create_message(
        sender="planner",
        recipient="executor",
        kind="task",
        payload={"action": "lookup"},
    )

    with pytest.raises(CommunicationError) as exc_info:
        engine.validate(
            make_message(
                sender="planner",
                recipient="executor",
                kind="task",
                payload={"action": "lookup"},
            )
        )

    assert exc_info.value.failure_type == FailureType.STEP_LIMIT
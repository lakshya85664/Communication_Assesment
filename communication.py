from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4


class MessageKind(str, Enum):
    TASK = "task"
    RESULT = "result"
    ACK = "ack"


class FailureType(str, Enum):
    VALIDATION = "validation"
    UNSUPPORTED_KIND = "unsupported_kind"
    SECRET_DETECTED = "secret_detected"
    STEP_LIMIT = "step_limit"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    MESSAGE_NOT_FOUND = "message_not_found"
    DUPLICATE_ROUTE = "duplicate_route"
    ROUTE_NOT_FOUND = "route_not_found"
    DUPLICATE_ACK = "duplicate_ack"
    DEAD_LETTER_DUPLICATE = "dead_letter_duplicate"
    CORRELATION_NOT_FOUND = "correlation_not_found"


class CommunicationError(Exception):
    def __init__(
        self,
        message: str,
        failure_type: FailureType,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type


@dataclass(frozen=True)
class Message:
    message_id: str
    sender: str
    recipient: str
    kind: str
    payload: dict[str, Any]
    correlation_id: str


@dataclass(frozen=True)
class DeadLetter:
    message: Message
    failure_type: str
    reason: str
    retryable: bool


@dataclass(frozen=True)
class CommunicationEvent:
    step: int
    event: str
    correlation_id: str | None
    details: dict[str, Any]

    @property
    def event_type(self) -> str:
        return self.event


_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"secret\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*\S+", re.IGNORECASE),
]


def contains_secret_like_value(value: Any) -> bool:
    if isinstance(value, str):
        return any(
            pattern.search(value)
            for pattern in _SECRET_PATTERNS
        )

    if isinstance(value, dict):
        return any(
            contains_secret_like_value(key)
            or contains_secret_like_value(item)
            for key, item in value.items()
        )

    if isinstance(value, (list, tuple, set)):
        return any(
            contains_secret_like_value(item)
            for item in value
        )

    return False


def _validate_non_empty_string(
    value: Any,
    field_name: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CommunicationError(
            f"{field_name} must be a non-empty string.",
            FailureType.VALIDATION,
        )


def validate_message(message: Message) -> bool:
    if not isinstance(message, Message):
        raise CommunicationError(
            "Message must be a Message instance.",
            FailureType.VALIDATION,
        )

    _validate_non_empty_string(
        message.message_id,
        "message_id",
    )

    _validate_non_empty_string(
        message.sender,
        "sender",
    )

    _validate_non_empty_string(
        message.recipient,
        "recipient",
    )

    _validate_non_empty_string(
        message.kind,
        "kind",
    )

    _validate_non_empty_string(
        message.correlation_id,
        "correlation_id",
    )

    if not isinstance(message.payload, dict):
        raise CommunicationError(
            "payload must be a dictionary.",
            FailureType.VALIDATION,
        )

    try:
        MessageKind(message.kind)
    except ValueError:
        raise CommunicationError(
            f"Unsupported message kind: {message.kind!r}.",
            FailureType.UNSUPPORTED_KIND,
        )

    if contains_secret_like_value(message.payload):
        raise CommunicationError(
            "Secret-like value detected in message payload.",
            FailureType.SECRET_DETECTED,
        )

    return True


def make_message(
    sender: str,
    recipient: str,
    kind: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> Message:
    _validate_non_empty_string(sender, "sender")
    _validate_non_empty_string(recipient, "recipient")

    if not isinstance(payload, dict):
        raise CommunicationError(
            "payload must be a dictionary.",
            FailureType.VALIDATION,
        )

    message = Message(
        message_id=str(uuid4()),
        sender=sender,
        recipient=recipient,
        kind=kind,
        payload=payload,
        correlation_id=correlation_id or str(uuid4()),
    )

    validate_message(message)

    return message


def message_to_dict(message: Message) -> dict[str, Any]:
    """
    Return the public message contract.

    message_id is intentionally excluded because the
    assessment contract exposes only the communication fields.
    """

    return {
        "kind": message.kind,
        "sender": message.sender,
        "recipient": message.recipient,
        "payload": message.payload,
        "correlation_id": message.correlation_id,
    }


class CommunicationEngine:

    def __init__(self, max_steps: int = 20) -> None:
        if not isinstance(max_steps, int) or max_steps <= 0:
            raise CommunicationError(
                "max_steps must be a positive integer.",
                FailureType.VALIDATION,
            )

        self.max_steps = max_steps
        self.step_count = 0

        self.routes: dict[
            str,
            Callable[[Message], Any],
        ] = {}

        # Latest message for each correlation ID.
        self.messages: dict[str, Message] = {}

        # Complete message history for each correlation ID.
        self.message_history: dict[
            str,
            list[Message],
        ] = {}

        self.acknowledged: set[str] = set()

        self.dead_letters: dict[
            str,
            DeadLetter,
        ] = {}

        self.trace: list[CommunicationEvent] = []

    @property
    def steps(self) -> int:
        return self.step_count

    def _consume_step(self) -> None:
        if self.step_count >= self.max_steps:
            raise CommunicationError(
                f"Communication step limit of "
                f"{self.max_steps} exceeded.",
                FailureType.STEP_LIMIT,
            )

        self.step_count += 1

    def record(
        self,
        event_type: str,
        correlation_id: str | None = None,
        **details: Any,
    ) -> CommunicationEvent:

        self._consume_step()

        event = CommunicationEvent(
            step=self.step_count,
            event=event_type,
            correlation_id=correlation_id,
            details=details,
        )

        self.trace.append(event)

        return event

    def create_message(
        self,
        sender: str,
        recipient: str,
        kind: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> Message:

        message = make_message(
            sender=sender,
            recipient=recipient,
            kind=kind,
            payload=payload,
            correlation_id=correlation_id,
        )

        self.messages[message.correlation_id] = message

        self.message_history.setdefault(
            message.correlation_id,
            [],
        ).append(message)

        self.record(
            "message_created",
            correlation_id=message.correlation_id,
            message_id=message.message_id,
            sender=message.sender,
            recipient=message.recipient,
            kind=message.kind,
        )

        return message

    def validate(
        self,
        message: Message,
    ) -> bool:

        result = validate_message(message)

        self.record(
            "message_validated",
            correlation_id=message.correlation_id,
            message_id=message.message_id,
        )

        return result

    def register_route(
        self,
        recipient: str,
        handler: Callable[[Message], Any],
    ) -> None:

        _validate_non_empty_string(
            recipient,
            "recipient",
        )

        if not callable(handler):
            raise CommunicationError(
                "Route handler must be callable.",
                FailureType.VALIDATION,
            )

        if recipient in self.routes:
            raise CommunicationError(
                f"Route for recipient "
                f"{recipient!r} is already registered.",
                FailureType.DUPLICATE_ROUTE,
            )

        self.routes[recipient] = handler

        self.record(
            "route_registered",
            recipient=recipient,
        )

    def route_message(
        self,
        message: Message,
    ) -> Any:

        self.validate(message)

        handler = self.routes.get(
            message.recipient
        )

        if handler is None:
            self.record(
                "route_rejected",
                correlation_id=message.correlation_id,
                message_id=message.message_id,
                recipient=message.recipient,
                reason="route_not_found",
            )

            raise CommunicationError(
                f"No route registered for recipient "
                f"{message.recipient!r}.",
                FailureType.ROUTE_NOT_FOUND,
            )

        result = handler(message)

        if contains_secret_like_value(result):
            self.record(
                "route_rejected",
                correlation_id=message.correlation_id,
                message_id=message.message_id,
                recipient=message.recipient,
                reason="secret_detected_in_handler_result",
            )

            raise CommunicationError(
                "Secret-like value detected in handler result.",
                FailureType.SECRET_DETECTED,
            )

        self.record(
            "message_routed",
            correlation_id=message.correlation_id,
            message_id=message.message_id,
            recipient=message.recipient,
        )

        return result

    def acknowledge(
        self,
        message: Message,
        receiver: str | None = None,
    ) -> Message:

        self.validate(message)

        correlation_id = message.correlation_id

        if correlation_id not in self.messages:
            raise CommunicationError(
                f"Cannot acknowledge unknown message "
                f"{correlation_id!r}.",
                FailureType.MESSAGE_NOT_FOUND,
            )

        if correlation_id in self.acknowledged:
            raise CommunicationError(
                f"Message {correlation_id!r} "
                f"is already acknowledged.",
                FailureType.DUPLICATE_ACK,
            )

        if receiver is None:
            ack_sender = message.recipient
        else:
            ack_sender = receiver

        _validate_non_empty_string(
            ack_sender,
            "receiver",
        )

        ack = Message(
            message_id=str(uuid4()),
            sender=ack_sender,
            recipient=message.sender,
            kind=MessageKind.ACK.value,
            payload={
                "acknowledged": True,
                "original_kind": message.kind,
            },
            correlation_id=message.correlation_id,
        )

        validate_message(ack)

        self.acknowledged.add(
            correlation_id
        )

        self.record(
            "message_acknowledged",
            correlation_id=correlation_id,
            message_id=message.message_id,
            ack_message_id=ack.message_id,
            receiver=ack_sender,
        )

        return ack

    def dead_letter(
        self,
        message: Message,
        failure_type: FailureType | str,
        reason: str,
    ) -> DeadLetter:

        self.validate(message)

        _validate_non_empty_string(
            reason,
            "reason",
        )

        if contains_secret_like_value(reason):
            raise CommunicationError(
                "Secret-like value detected "
                "in dead-letter reason.",
                FailureType.SECRET_DETECTED,
            )

        correlation_id = message.correlation_id

        if correlation_id in self.dead_letters:
            raise CommunicationError(
                f"Message {correlation_id!r} is already "
                f"in the dead-letter store.",
                FailureType.DEAD_LETTER_DUPLICATE,
            )

        try:
            failure = FailureType(
                failure_type
            )
        except ValueError:
            raise CommunicationError(
                f"Unsupported failure type: "
                f"{failure_type!r}.",
                FailureType.VALIDATION,
            )

        retryable = (
            failure == FailureType.TRANSIENT
        )

        dead_letter = DeadLetter(
            message=message,
            failure_type=failure.value,
            reason=reason,
            retryable=retryable,
        )

        self.dead_letters[
            correlation_id
        ] = dead_letter

        self.record(
            "message_dead_lettered",
            correlation_id=correlation_id,
            message_id=message.message_id,
            failure_type=failure.value,
            retryable=retryable,
        )

        return dead_letter

    def get_dead_letter(
        self,
        correlation_id: str,
    ) -> DeadLetter:

        _validate_non_empty_string(
            correlation_id,
            "correlation_id",
        )

        dead_letter = self.dead_letters.get(
            correlation_id
        )

        if dead_letter is None:
            raise CommunicationError(
                f"No dead-letter entry found for "
                f"correlation ID {correlation_id!r}.",
                FailureType.MESSAGE_NOT_FOUND,
            )

        self.record(
            "dead_letter_retrieved",
            correlation_id=correlation_id,
        )

        return dead_letter

    def correlation_trace(
        self,
        correlation_id: str,
    ) -> dict[str, Any]:

        _validate_non_empty_string(
            correlation_id,
            "correlation_id",
        )

        try:
            UUID(correlation_id)
        except (
            ValueError,
            AttributeError,
            TypeError,
        ):
            raise CommunicationError(
                "correlation_id must be a valid UUID.",
                FailureType.VALIDATION,
            )

        matching_events = [
            event
            for event in self.trace
            if event.correlation_id
            == correlation_id
        ]

        related_messages = (
            self.message_history.get(
                correlation_id,
                [],
            )
        )

        if (
            not matching_events
            and not related_messages
        ):
            raise CommunicationError(
                f"No communication trace found for "
                f"correlation ID {correlation_id!r}.",
                FailureType.CORRELATION_NOT_FOUND,
            )

        result = {
            "correlation_id": correlation_id,
            "message_count": len(
                related_messages
            ),
            "event_count": len(
                matching_events
            ),
            "messages": [
                message_to_dict(message)
                for message in related_messages
            ],
            "events": [
                asdict(event)
                for event in matching_events
            ],
        }

        self.record(
            "correlation_trace_computed",
            correlation_id=correlation_id,
            message_count=len(
                related_messages
            ),
            event_count=len(
                matching_events
            ),
        )

        return result

    def save_trace(
        self,
        path: str | Path,
    ) -> Path:

        output_path = Path(path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "events": [
                asdict(event)
                for event in self.trace
            ],
        }

        output_path.write_text(
            json.dumps(
                payload,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        return output_path


def save_trace(
    source: CommunicationEngine
    | list[CommunicationEvent],
    path: str | Path,
) -> Path:

    output_path = Path(path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if isinstance(
        source,
        CommunicationEngine,
    ):
        payload = {
            "step_count": source.step_count,
            "max_steps": source.max_steps,
            "events": [
                asdict(event)
                for event in source.trace
            ],
        }
    else:
        payload = {
            "events": [
                asdict(event)
                for event in source
            ],
        }

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return output_path
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.game.models import Coord


class MessageValidationError(Exception):
    """Raised when an incoming WebSocket frame fails size, JSON, or schema validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MakeMoveMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["make_move"]
    from_pos: Coord = Field(alias="from")
    landings: list[Coord] = Field(min_length=1, max_length=12)
    revision: int = Field(ge=0)


class ResignMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["resign"]


class RequestRematchMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["request_rematch"]


class PingMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ping"]


ClientMessage = Annotated[
    MakeMoveMessage | ResignMessage | RequestRematchMessage | PingMessage,
    Field(discriminator="type"),
]

_CLIENT_MESSAGE_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw_text: str, *, max_bytes: int = 4096) -> ClientMessage:
    """Validate message size, JSON syntax, and strict client message schema."""
    encoded_len = len(raw_text.encode("utf-8", errors="replace"))
    if encoded_len > max_bytes:
        raise MessageValidationError(
            "message_too_large",
            f"Message exceeds maximum size of {max_bytes} bytes.",
        )

    try:
        parsed_json = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise MessageValidationError(
            "invalid_json", "Message must be valid JSON."
        ) from exc

    if not isinstance(parsed_json, dict) or "type" not in parsed_json:
        raise MessageValidationError(
            "invalid_message", "Message must be a JSON object with a 'type' field."
        )

    try:
        return _CLIENT_MESSAGE_ADAPTER.validate_python(parsed_json)
    except ValidationError as exc:
        raise MessageValidationError(
            "invalid_message",
            "Unsupported or malformed client message.",
        ) from exc

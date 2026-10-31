import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.game.config import DEFAULT_RULES_CONFIG, RulesConfig
from app.game.models import Color, GameState, GameStatus


class PlayerPublicView(BaseModel):
    """Publicly safe view of a player seat (never includes player_token)."""

    name: str
    color: Color
    connected: bool = False
    reconnect_grace_remaining_seconds: int | None = None


class RoomSnapshot(BaseModel):
    """Authoritative room + game snapshot broadcast to clients."""

    room_code: str
    invite_url: str
    players: dict[Color, PlayerPublicView | None]
    game: GameState
    your_color: Color | None = None
    rematch_requested_by: list[Color] = Field(default_factory=list)
    match_number: int = 1
    disconnect_grace_seconds: int = 120


class CreateRoomResult(BaseModel):
    """Result returned to the room creator."""

    room_code: str
    invite_url: str
    player_token: str
    player_color: Color
    room_status: GameStatus
    snapshot: RoomSnapshot


class JoinRoomResult(BaseModel):
    """Result returned when joining or re-claiming a seat in a room."""

    room_code: str
    invite_url: str
    player_token: str
    player_color: Color
    room_status: GameStatus
    reconnected: bool = False
    snapshot: RoomSnapshot


class RematchResult(BaseModel):
    """Result of a player requesting a rematch."""

    started: bool
    snapshot: RoomSnapshot


@dataclass
class PlayerSeat:
    """Internal server-only player seat record."""

    seat_id: str
    token: str
    name: str
    color: Color
    connected: bool = False
    disconnected_at: float | None = None
    last_taunt_at: float | None = None


@dataclass
class Room:
    """Internal in-memory room record guarded by an asyncio.Lock."""

    room_code: str
    created_at: float
    updated_at: float
    game_state: GameState
    rules_config: RulesConfig = DEFAULT_RULES_CONFIG
    seats: list[PlayerSeat] = field(default_factory=list)
    rematch_requests: set[str] = field(default_factory=set)  # stores seat_ids
    match_number: int = 1
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def seat_by_token(self, token: str | None) -> PlayerSeat | None:
        if not token:
            return None
        for seat in self.seats:
            if seat.token == token:
                return seat
        return None

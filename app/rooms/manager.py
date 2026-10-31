import re
import secrets
import time
import unicodedata
from collections.abc import Callable

from app.game.config import DEFAULT_RULES_CONFIG, RulesConfig
from app.game.engine import (
    IllegalMoveError,
    activate_game_state,
    apply_move,
    create_initial_game_state,
    resign_game,
)
from app.game.models import Color, MoveAttempt, opponent_of
from app.rooms.models import (
    CreateRoomResult,
    JoinRoomResult,
    PlayerPublicView,
    PlayerSeat,
    RematchResult,
    Room,
    RoomSnapshot,
)

# Unambiguous uppercase characters (excludes 0, O, 1, I, L)
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_PATTERN = re.compile(r"^[A-Z2-9]{4,12}$")
MAX_PLAYER_NAME_LENGTH = 20


class RoomError(Exception):
    """Domain error for room lookup, authorization, validation, or capacity."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RoomMoveRejected(Exception):
    """Raised when an authenticated player's move is rejected by turn, revision, or rules."""

    def __init__(
        self,
        code: str,
        message: str,
        latest_snapshot: RoomSnapshot,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.latest_snapshot = latest_snapshot


def sanitize_player_name(raw_name: str) -> str:
    """Validate and clean a player's display name (supports Arabic & Latin scripts)."""
    if not isinstance(raw_name, str):
        raise RoomError("invalid_player_name", "Display name must be text.", 422)

    # Strip control/format characters and collapse runs of whitespace
    cleaned_chars = [
        ch for ch in raw_name if not unicodedata.category(ch).startswith("C")
    ]
    collapsed = " ".join("".join(cleaned_chars).split())

    if not collapsed:
        raise RoomError("invalid_player_name", "Please enter a display name.", 422)

    if len(collapsed) > MAX_PLAYER_NAME_LENGTH:
        raise RoomError(
            "invalid_player_name",
            f"Display name must be at most {MAX_PLAYER_NAME_LENGTH} characters.",
            422,
        )

    return collapsed


def normalize_room_code(raw_code: str) -> str:
    """Normalize and validate room code format."""
    if not isinstance(raw_code, str):
        raise RoomError("invalid_room_code", "Invalid room code.", 422)
    code = raw_code.strip().upper()
    if not ROOM_CODE_PATTERN.match(code):
        raise RoomError("invalid_room_code", "Room code format is invalid.", 422)
    return code


class RoomManager:
    """Authoritative in-memory registry for private Moroccan Dama rooms."""

    def __init__(
        self,
        *,
        room_code_length: int = 6,
        waiting_room_ttl_seconds: int = 1800,
        disconnect_grace_seconds: int = 120,
        finished_room_ttl_seconds: int = 1800,
        rules_config: RulesConfig = DEFAULT_RULES_CONFIG,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.room_code_length = room_code_length
        self.waiting_room_ttl_seconds = waiting_room_ttl_seconds
        self.disconnect_grace_seconds = disconnect_grace_seconds
        self.finished_room_ttl_seconds = finished_room_ttl_seconds
        self.rules_config = rules_config
        self._clock = clock
        self._rooms: dict[str, Room] = {}

    def _is_room_expired(self, room: Room, now: float) -> bool:
        status = room.game_state.status
        if status == "waiting":
            return (now - room.created_at) > self.waiting_room_ttl_seconds
        if status == "finished":
            return (now - room.updated_at) > self.finished_room_ttl_seconds
        # Active room: expire if all seats are disconnected past grace period
        if room.seats and all(not s.connected for s in room.seats):
            disconnect_times = [
                s.disconnected_at for s in room.seats if s.disconnected_at is not None
            ]
            if disconnect_times and (now - max(disconnect_times)) > self.disconnect_grace_seconds:
                return True
            if not disconnect_times and (now - room.updated_at) > self.waiting_room_ttl_seconds:
                return True
        return False

    def cleanup_expired(self) -> int:
        """Remove expired rooms and return count removed."""
        now = self._clock()
        expired_codes = [
            code for code, room in self._rooms.items() if self._is_room_expired(room, now)
        ]
        for code in expired_codes:
            self._rooms.pop(code, None)
        return len(expired_codes)

    def _get_live_room(self, raw_code: str) -> Room:
        code = normalize_room_code(raw_code)
        room = self._rooms.get(code)
        if room is None:
            raise RoomError("room_not_found", "Room not found or has expired.", 404)
        now = self._clock()
        if self._is_room_expired(room, now):
            self._rooms.pop(code, None)
            raise RoomError("room_expired", "This room has expired.", 410)
        return room

    def _generate_unique_code(self) -> str:
        for _ in range(64):
            code = "".join(
                secrets.choice(ROOM_CODE_ALPHABET) for _ in range(self.room_code_length)
            )
            if code not in self._rooms:
                return code
        raise RuntimeError("Unable to allocate unique room code.")

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(24)

    def _build_snapshot(
        self, room: Room, viewer_color: Color | None = None
    ) -> RoomSnapshot:
        now = self._clock()
        players: dict[Color, PlayerPublicView | None] = {"white": None, "black": None}
        for seat in room.seats:
            remaining: int | None = None
            if not seat.connected and seat.disconnected_at is not None:
                elapsed = now - seat.disconnected_at
                remaining = max(0, round(self.disconnect_grace_seconds - elapsed))
            players[seat.color] = PlayerPublicView(
                name=seat.name,
                color=seat.color,
                connected=seat.connected,
                reconnect_grace_remaining_seconds=remaining,
            )

        rematch_colors: list[Color] = [
            seat.color for seat in room.seats if seat.seat_id in room.rematch_requests
        ]

        return RoomSnapshot(
            room_code=room.room_code,
            invite_url=f"/game/{room.room_code}",
            players=players,
            game=room.game_state,
            your_color=viewer_color,
            rematch_requested_by=rematch_colors,
            match_number=room.match_number,
            disconnect_grace_seconds=self.disconnect_grace_seconds,
        )

    def create_room(self, player_name: str) -> CreateRoomResult:
        """Create a new private room and allocate the creator's seat."""
        self.cleanup_expired()
        clean_name = sanitize_player_name(player_name)
        now = self._clock()
        code = self._generate_unique_code()
        token = self._generate_token()

        creator_seat = PlayerSeat(
            seat_id="seat_1",
            token=token,
            name=clean_name,
            color="white",
            connected=False,
        )
        initial_state = create_initial_game_state(
            config=self.rules_config, status="waiting"
        )
        room = Room(
            room_code=code,
            created_at=now,
            updated_at=now,
            rules_config=self.rules_config,
            seats=[creator_seat],
            game_state=initial_state,
        )
        self._rooms[code] = room
        snapshot = self._build_snapshot(room, viewer_color="white")
        return CreateRoomResult(
            room_code=code,
            invite_url=f"/game/{code}",
            player_token=token,
            player_color="white",
            room_status=room.game_state.status,
            snapshot=snapshot,
        )

    def join_room(
        self,
        room_code: str,
        player_name: str | None = None,
        *,
        existing_token: str | None = None,
    ) -> JoinRoomResult:
        """Join an open second seat or idempotently reclaim an existing seat by token."""
        self.cleanup_expired()
        room = self._get_live_room(room_code)
        now = self._clock()

        existing_seat = room.seat_by_token(existing_token)
        if existing_seat is not None:
            room.updated_at = now
            snapshot = self._build_snapshot(room, viewer_color=existing_seat.color)
            return JoinRoomResult(
                room_code=room.room_code,
                invite_url=f"/game/{room.room_code}",
                player_token=existing_seat.token,
                player_color=existing_seat.color,
                room_status=room.game_state.status,
                reconnected=True,
                snapshot=snapshot,
            )

        if len(room.seats) >= 2:
            raise RoomError("room_full", "This room already has two players.", 409)

        clean_name = sanitize_player_name(player_name or "")
        assigned_color: Color = opponent_of(room.seats[0].color)
        token = self._generate_token()
        second_seat = PlayerSeat(
            seat_id="seat_2",
            token=token,
            name=clean_name,
            color=assigned_color,
            connected=False,
        )
        room.seats.append(second_seat)
        room.game_state = activate_game_state(room.game_state)
        room.updated_at = now

        snapshot = self._build_snapshot(room, viewer_color=assigned_color)
        return JoinRoomResult(
            room_code=room.room_code,
            invite_url=f"/game/{room.room_code}",
            player_token=token,
            player_color=assigned_color,
            room_status=room.game_state.status,
            reconnected=False,
            snapshot=snapshot,
        )

    def get_public_snapshot(self, room_code: str) -> RoomSnapshot:
        """Return a token-free snapshot of the room."""
        room = self._get_live_room(room_code)
        return self._build_snapshot(room, viewer_color=None)

    def authenticate_seat(self, room_code: str, token: str) -> tuple[Room, PlayerSeat]:
        """Verify room existence and seat token."""
        room = self._get_live_room(room_code)
        seat = room.seat_by_token(token)
        if seat is None:
            raise RoomError(
                "unauthorized", "Invalid or missing player seat token.", 403
            )
        return room, seat

    def get_player_snapshot(self, room_code: str, token: str) -> RoomSnapshot:
        """Return an authoritative snapshot personalized with `your_color`."""
        room, seat = self.authenticate_seat(room_code, token)
        return self._build_snapshot(room, viewer_color=seat.color)

    def mark_connected(self, room_code: str, token: str) -> RoomSnapshot:
        """Mark a seat's live WebSocket as connected."""
        room, seat = self.authenticate_seat(room_code, token)
        seat.connected = True
        seat.disconnected_at = None
        room.updated_at = self._clock()
        return self._build_snapshot(room, viewer_color=seat.color)

    def mark_disconnected(self, room_code: str, token: str) -> RoomSnapshot:
        """Mark a seat as disconnected while preserving the seat during grace period."""
        room, seat = self.authenticate_seat(room_code, token)
        now = self._clock()
        seat.connected = False
        seat.disconnected_at = now
        room.updated_at = now
        return self._build_snapshot(room, viewer_color=seat.color)

    async def submit_move(
        self,
        room_code: str,
        token: str,
        move: MoveAttempt,
        client_revision: int,
    ) -> RoomSnapshot:
        """Atomically validate and apply a complete turn for the authenticated seat."""
        room, seat = self.authenticate_seat(room_code, token)
        async with room.lock:
            if room.game_state.status != "active":
                raise RoomMoveRejected(
                    "game_not_active",
                    "The match is not currently active.",
                    self._build_snapshot(room, viewer_color=seat.color),
                )

            if client_revision != room.game_state.revision:
                raise RoomMoveRejected(
                    "stale_revision",
                    "Your board state was out of date; synchronized with latest state.",
                    self._build_snapshot(room, viewer_color=seat.color),
                )

            if seat.color != room.game_state.current_turn:
                raise RoomMoveRejected(
                    "not_your_turn",
                    "It is currently your opponent's turn.",
                    self._build_snapshot(room, viewer_color=seat.color),
                )

            try:
                next_state = apply_move(room.game_state, move)
            except IllegalMoveError as exc:
                raise RoomMoveRejected(
                    exc.code,
                    exc.message,
                    self._build_snapshot(room, viewer_color=seat.color),
                ) from exc

            room.game_state = next_state
            room.updated_at = self._clock()
            if next_state.status == "finished":
                room.rematch_requests.clear()

            return self._build_snapshot(room, viewer_color=seat.color)

    async def resign(self, room_code: str, token: str) -> RoomSnapshot:
        """Resign the current active match on behalf of the authenticated seat."""
        room, seat = self.authenticate_seat(room_code, token)
        async with room.lock:
            try:
                room.game_state = resign_game(room.game_state, seat.color)
            except IllegalMoveError as exc:
                raise RoomError(exc.code, exc.message, 409) from exc

            room.rematch_requests.clear()
            room.updated_at = self._clock()
            return self._build_snapshot(room, viewer_color=seat.color)

    async def request_rematch(self, room_code: str, token: str) -> RematchResult:
        """Record a player's rematch vote and start a new match once both players accept."""
        room, seat = self.authenticate_seat(room_code, token)
        async with room.lock:
            if room.game_state.status != "finished" or len(room.seats) < 2:
                raise RoomError(
                    "game_not_finished",
                    "Rematch can only be requested after the match ends.",
                    409,
                )

            room.rematch_requests.add(seat.seat_id)
            room.updated_at = self._clock()

            if len(room.rematch_requests) < 2:
                return RematchResult(
                    started=False,
                    snapshot=self._build_snapshot(room, viewer_color=seat.color),
                )

            # Both players requested a rematch -> swap colors and start fresh board
            room.seats[0].color, room.seats[1].color = (
                room.seats[1].color,
                room.seats[0].color,
            )
            prev_revision = room.game_state.revision
            fresh_state = create_initial_game_state(
                config=room.rules_config, status="active"
            )
            fresh_state.revision = prev_revision + 1
            room.game_state = fresh_state
            room.rematch_requests.clear()
            room.match_number += 1

            return RematchResult(
                started=True,
                snapshot=self._build_snapshot(room, viewer_color=seat.color),
            )

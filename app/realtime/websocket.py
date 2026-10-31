import contextlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.game.models import MoveAttempt
from app.realtime.messages import (
    MakeMoveMessage,
    MessageValidationError,
    PingMessage,
    RequestRematchMessage,
    ResignMessage,
    SendTauntMessage,
    parse_client_message,
)
from app.rooms.manager import RoomError, RoomManager, RoomMoveRejected
from app.rooms.models import RoomSnapshot

router = APIRouter()
TAUNT_COOLDOWN_SECONDS = 2.0


@dataclass
class ActiveSocketEntry:
    seat_id: str
    token: str
    websocket: WebSocket


class SlidingWindowRateLimiter:
    """Per-connection message rate limiter to guard against accidental flooding."""

    def __init__(self, max_messages_per_second: int = 15) -> None:
        self.max_messages = max(1, max_messages_per_second)
        self._timestamps: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        cutoff = now - 1.0
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_messages:
            return False
        self._timestamps.append(now)
        return True


class ConnectionHub:
    """Tracks live WebSocket connections per room and seat, handling reconnect races safely."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, ActiveSocketEntry]] = {}

    async def register(
        self, room_code: str, seat_id: str, token: str, websocket: WebSocket
    ) -> None:
        room_map = self._rooms.setdefault(room_code, {})
        previous = room_map.get(seat_id)
        room_map[seat_id] = ActiveSocketEntry(
            seat_id=seat_id, token=token, websocket=websocket
        )
        if previous is not None and previous.websocket is not websocket:
            with contextlib.suppress(Exception):
                await previous.websocket.close(
                    code=4000, reason="Superseded by new connection"
                )

    def unregister(self, room_code: str, seat_id: str, websocket: WebSocket) -> bool:
        """Remove socket only if it is still the active socket for `seat_id`."""
        room_map = self._rooms.get(room_code)
        if not room_map:
            return False
        current = room_map.get(seat_id)
        if current is None or current.websocket is not websocket:
            return False
        del room_map[seat_id]
        if not room_map:
            self._rooms.pop(room_code, None)
        return True

    async def send_safe(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await websocket.send_json(payload)

    async def broadcast_personalized(
        self,
        room_code: str,
        room_manager: RoomManager,
        payload_builder: Callable[[RoomSnapshot], dict[str, Any]],
        *,
        exclude_seat_id: str | None = None,
    ) -> None:
        room_map = self._rooms.get(room_code)
        if not room_map:
            return

        entries = list(room_map.values())
        for entry in entries:
            if exclude_seat_id is not None and entry.seat_id == exclude_seat_id:
                continue
            try:
                snap = room_manager.get_player_snapshot(room_code, entry.token)
            except RoomError:
                continue
            await self.send_safe(entry.websocket, payload_builder(snap))

    async def broadcast_raw(self, room_code: str, payload: dict[str, Any]) -> None:
        room_map = self._rooms.get(room_code)
        if not room_map:
            return
        for entry in list(room_map.values()):
            await self.send_safe(entry.websocket, payload)


@router.websocket("/ws/{room_code}")
async def room_websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    token: str = Query(default=""),
) -> None:
    await websocket.accept()

    room_manager: RoomManager = websocket.app.state.room_manager
    hub: ConnectionHub = websocket.app.state.connection_hub
    max_msg_bytes: int = websocket.app.state.max_ws_message_bytes
    rate_limit: int = websocket.app.state.ws_rate_limit_per_second

    try:
        room, seat = room_manager.authenticate_seat(room_code, token)
    except RoomError as exc:
        await hub.send_safe(
            websocket,
            {"type": "error", "code": exc.code, "message": exc.message},
        )
        close_code = 4404 if exc.status_code in (404, 410) else 4403
        await websocket.close(code=close_code)
        return

    canonical_code = room.room_code
    seat_id = seat.seat_id
    was_disconnected = seat.disconnected_at is not None

    await hub.register(canonical_code, seat_id, token, websocket)
    own_snapshot = room_manager.mark_connected(canonical_code, token)
    await hub.send_safe(
        websocket,
        {
            "type": "room_state",
            "room": own_snapshot.model_dump(mode="json", by_alias=True),
        },
    )

    if was_disconnected:
        await hub.broadcast_personalized(
            canonical_code,
            room_manager,
            lambda snap: {
                "type": "player_reconnected",
                "color": seat.color,
                "room": snap.model_dump(mode="json", by_alias=True),
            },
            exclude_seat_id=seat_id,
        )
    else:
        await hub.broadcast_personalized(
            canonical_code,
            room_manager,
            lambda snap: {
                "type": "room_state",
                "room": snap.model_dump(mode="json", by_alias=True),
            },
            exclude_seat_id=seat_id,
        )

    limiter = SlidingWindowRateLimiter(max_messages_per_second=rate_limit)

    try:
        while True:
            raw_text = await websocket.receive_text()

            if not limiter.allow():
                await hub.send_safe(
                    websocket,
                    {
                        "type": "error",
                        "code": "rate_limited",
                        "message": "Too many messages sent; please slow down.",
                    },
                )
                continue

            try:
                msg = parse_client_message(raw_text, max_bytes=max_msg_bytes)
            except MessageValidationError as exc:
                await hub.send_safe(
                    websocket,
                    {"type": "error", "code": exc.code, "message": exc.message},
                )
                continue

            if isinstance(msg, PingMessage):
                await hub.send_safe(websocket, {"type": "pong"})
                continue

            if isinstance(msg, SendTauntMessage):
                now_mono = time.monotonic()
                if (
                    seat.last_taunt_at is not None
                    and (now_mono - seat.last_taunt_at) < TAUNT_COOLDOWN_SECONDS
                ):
                    await hub.send_safe(
                        websocket,
                        {
                            "type": "error",
                            "code": "taunt_cooldown",
                            "message": "Easy there! Wait a moment before sending another line.",
                        },
                    )
                    continue

                seat.last_taunt_at = now_mono
                await hub.broadcast_raw(
                    canonical_code,
                    {
                        "type": "taunt_sent",
                        "taunt_id": msg.taunt_id,
                        "from_color": seat.color,
                        "sender_name": seat.name,
                    },
                )
                continue

            if isinstance(msg, MakeMoveMessage):
                attempt = MoveAttempt(from_pos=msg.from_pos, landings=msg.landings)
                try:
                    updated_snap = await room_manager.submit_move(
                        canonical_code,
                        token,
                        attempt,
                        client_revision=msg.revision,
                    )
                except RoomMoveRejected as exc:
                    await hub.send_safe(
                        websocket,
                        {
                            "type": "move_rejected",
                            "code": exc.code,
                            "message": exc.message,
                            "room": exc.latest_snapshot.model_dump(
                                mode="json", by_alias=True
                            ),
                        },
                    )
                    continue
                except RoomError as exc:
                    await hub.send_safe(
                        websocket,
                        {"type": "error", "code": exc.code, "message": exc.message},
                    )
                    continue

                move_payload = (
                    updated_snap.game.last_move.model_dump(mode="json", by_alias=True)
                    if updated_snap.game.last_move is not None
                    else None
                )
                new_revision = updated_snap.game.revision

                await hub.broadcast_personalized(
                    canonical_code,
                    room_manager,
                    lambda snap, move=move_payload, rev=new_revision: {
                        "type": "move_applied",
                        "move": move,
                        "revision": rev,
                        "room": snap.model_dump(mode="json", by_alias=True),
                    },
                )

                if updated_snap.game.status == "finished":
                    await hub.broadcast_personalized(
                        canonical_code,
                        room_manager,
                        lambda snap: {
                            "type": "game_finished",
                            "winner": snap.game.winner,
                            "finish_reason": snap.game.finish_reason,
                            "room": snap.model_dump(mode="json", by_alias=True),
                        },
                    )
                continue

            if isinstance(msg, ResignMessage):
                try:
                    resigned_snap = await room_manager.resign(canonical_code, token)
                except RoomError as exc:
                    await hub.send_safe(
                        websocket,
                        {"type": "error", "code": exc.code, "message": exc.message},
                    )
                    continue

                winner = resigned_snap.game.winner
                finish_reason = resigned_snap.game.finish_reason
                await hub.broadcast_personalized(
                    canonical_code,
                    room_manager,
                    lambda snap, w=winner, r=finish_reason: {
                        "type": "game_finished",
                        "winner": w,
                        "finish_reason": r,
                        "room": snap.model_dump(mode="json", by_alias=True),
                    },
                )
                continue

            if isinstance(msg, RequestRematchMessage):
                try:
                    rematch_res = await room_manager.request_rematch(
                        canonical_code, token
                    )
                except RoomError as exc:
                    await hub.send_safe(
                        websocket,
                        {"type": "error", "code": exc.code, "message": exc.message},
                    )
                    continue

                await hub.broadcast_personalized(
                    canonical_code,
                    room_manager,
                    lambda snap, started=rematch_res.started: {
                        "type": "rematch_status",
                        "started": started,
                        "requested_by": snap.rematch_requested_by,
                        "room": snap.model_dump(mode="json", by_alias=True),
                    },
                )
                continue

    except WebSocketDisconnect:
        pass
    finally:
        still_owned = hub.unregister(canonical_code, seat_id, websocket)
        if still_owned:
            try:
                current_seat_color = seat.color
                room_manager.mark_disconnected(canonical_code, token)
                await hub.broadcast_personalized(
                    canonical_code,
                    room_manager,
                    lambda snap: {
                        "type": "player_disconnected",
                        "color": current_seat_color,
                        "room": snap.model_dump(mode="json", by_alias=True),
                    },
                    exclude_seat_id=seat_id,
                )
            except RoomError:
                pass

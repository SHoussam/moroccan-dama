import asyncio

import pytest

from app.game.models import MoveAttempt
from app.rooms.manager import RoomError, RoomManager, RoomMoveRejected


class FakeClock:
    def __init__(self, initial: float = 1000.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_create_room_and_join_assigns_opposite_colors_and_hides_tokens():
    clock = FakeClock()
    mgr = RoomManager(clock=clock)

    created = mgr.create_room("Houssam")
    assert len(created.room_code) == 6
    assert all(ch not in "0O1IL" for ch in created.room_code)
    assert created.player_color == "white"
    assert len(created.player_token) >= 24
    assert created.room_status == "waiting"

    joined = mgr.join_room(created.room_code.lower(), "Amine")
    assert joined.room_code == created.room_code
    assert joined.player_color == "black"
    assert joined.player_token != created.player_token
    assert joined.snapshot.game.status == "active"

    # Public snapshot must not contain player tokens
    public = mgr.get_public_snapshot(created.room_code)
    serialized = public.model_dump_json()
    assert created.player_token not in serialized
    assert joined.player_token not in serialized


def test_third_player_rejected_but_existing_token_can_rejoin_idempotently():
    mgr = RoomManager(clock=FakeClock())
    p1 = mgr.create_room("Houssam")
    p2 = mgr.join_room(p1.room_code, "Friend")

    with pytest.raises(RoomError) as exc_info:
        mgr.join_room(p1.room_code, "Intruder")
    assert exc_info.value.code == "room_full"

    # Existing seat token re-opening invite link returns same seat without error
    rejoined = mgr.join_room(p1.room_code, "Houssam", existing_token=p1.player_token)
    assert rejoined.player_token == p1.player_token
    assert rejoined.player_color == "white"


def test_player_name_validation_and_arabic_names_supported():
    mgr = RoomManager(clock=FakeClock())
    arabic_room = mgr.create_room("  حسام  ")
    snap = mgr.get_public_snapshot(arabic_room.room_code)
    assert snap.players["white"].name == "حسام"

    with pytest.raises(RoomError) as exc_empty:
        mgr.create_room("   \n\t  ")
    assert exc_empty.value.code == "invalid_player_name"

    with pytest.raises(RoomError) as exc_long:
        mgr.create_room("A" * 25)
    assert exc_long.value.code == "invalid_player_name"


def test_waiting_room_and_finished_room_expiry():
    clock = FakeClock()
    mgr = RoomManager(
        clock=clock,
        waiting_room_ttl_seconds=1800,
        finished_room_ttl_seconds=1800,
    )
    created = mgr.create_room("Houssam")

    clock.advance(1801)
    with pytest.raises(RoomError) as exc_info:
        mgr.join_room(created.room_code, "LateFriend")
    assert exc_info.value.code in ("room_expired", "room_not_found")


def test_turn_authorization_and_stale_revision_protection():
    async def run() -> None:
        mgr = RoomManager(clock=FakeClock())
        p1 = mgr.create_room("Houssam")
        p2 = mgr.join_room(p1.room_code, "Friend")
        rev0 = p2.snapshot.game.revision

        # Invalid token cannot submit move
        with pytest.raises(RoomError) as exc_auth:
            await mgr.submit_move(
                p1.room_code,
                "forged-token",
                MoveAttempt(**{"from": (5, 0), "landings": [(4, 1)]}),
                client_revision=rev0,
            )
        assert exc_auth.value.code == "unauthorized"

        # Black cannot move on White's turn
        with pytest.raises(RoomMoveRejected) as exc_turn:
            await mgr.submit_move(
                p1.room_code,
                p2.player_token,
                MoveAttempt(**{"from": (2, 1), "landings": [(3, 0)]}),
                client_revision=rev0,
            )
        assert exc_turn.value.code == "not_your_turn"

        # White makes a valid opening move
        snap1 = await mgr.submit_move(
            p1.room_code,
            p1.player_token,
            MoveAttempt(**{"from": (5, 0), "landings": [(4, 1)]}),
            client_revision=rev0,
        )
        assert snap1.game.revision == rev0 + 1
        assert snap1.game.current_turn == "black"

        # Submitting with stale revision rev0 is rejected and returns latest snapshot
        with pytest.raises(RoomMoveRejected) as exc_stale:
            await mgr.submit_move(
                p1.room_code,
                p2.player_token,
                MoveAttempt(**{"from": (2, 1), "landings": [(3, 0)]}),
                client_revision=rev0,
            )
        assert exc_stale.value.code == "stale_revision"
        assert exc_stale.value.latest_snapshot.game.revision == snap1.game.revision

    asyncio.run(run())


def test_disconnect_grace_period_preserves_seat_and_reconnect_restores_it():
    clock = FakeClock()
    mgr = RoomManager(clock=clock, disconnect_grace_seconds=120)
    p1 = mgr.create_room("Houssam")
    p2 = mgr.join_room(p1.room_code, "Friend")

    mgr.mark_connected(p1.room_code, p1.player_token)
    mgr.mark_connected(p1.room_code, p2.player_token)

    snap_disc = mgr.mark_disconnected(p1.room_code, p2.player_token)
    assert snap_disc.players["black"].connected is False
    assert snap_disc.game.status == "active"
    assert snap_disc.game.winner is None

    # 60 seconds later (within 120s grace period), seat is still reserved & intruder rejected
    clock.advance(60)
    with pytest.raises(RoomError) as exc_full:
        mgr.join_room(p1.room_code, "Intruder")
    assert exc_full.value.code == "room_full"

    # Reconnect with original token restores live seat
    snap_reconn = mgr.mark_connected(p1.room_code, p2.player_token)
    assert snap_reconn.players["black"].connected is True
    assert snap_reconn.game.status == "active"


def test_resignation_and_mutual_rematch_flow():
    async def run() -> None:
        mgr = RoomManager(clock=FakeClock())
        p1 = mgr.create_room("Houssam")
        p2 = mgr.join_room(p1.room_code, "Friend")

        snap_resigned = await mgr.resign(p1.room_code, p1.player_token)
        assert snap_resigned.game.status == "finished"
        assert snap_resigned.game.winner == "black"
        assert snap_resigned.game.finish_reason == "resignation"
        rev_after_resign = snap_resigned.game.revision

        # First rematch request waits for second player
        rematch_1 = await mgr.request_rematch(p1.room_code, p1.player_token)
        assert rematch_1.started is False
        assert rematch_1.snapshot.game.status == "finished"
        assert len(rematch_1.snapshot.rematch_requested_by) == 1

        # Duplicate request by same player does not start rematch alone
        rematch_dup = await mgr.request_rematch(p1.room_code, p1.player_token)
        assert rematch_dup.started is False

        # Second player accepts -> new match starts with monotonically higher revision
        rematch_2 = await mgr.request_rematch(p1.room_code, p2.player_token)
        assert rematch_2.started is True
        assert rematch_2.snapshot.game.status == "active"
        assert rematch_2.snapshot.game.move_number == 0
        assert rematch_2.snapshot.game.revision > rev_after_resign
        assert rematch_2.snapshot.rematch_requested_by == []

    asyncio.run(run())

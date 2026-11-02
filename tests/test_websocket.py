from fastapi.testclient import TestClient

from app.main import create_app


def _drain_until_type(ws, target_type: str, max_msgs: int = 5) -> dict:
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg["type"] == target_type:
            return msg
        if msg["type"] == "error" and target_type != "error":
            raise AssertionError(
                f"Expected {target_type!r} but received error frame: {msg!r}"
            )
    raise AssertionError(f"Did not receive message of type {target_type!r}")


def test_http_create_join_public_state_and_third_player_rejection():
    app = create_app()
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        r1 = client.post("/api/rooms", json={"player_name": "Houssam"})
        assert r1.status_code == 201
        d1 = r1.json()
        code = d1["room_code"]
        assert d1["player_color"] == "white"
        assert d1["invite_url"] == f"/game/{code}"
        assert d1["room_status"] == "waiting"

        r2 = client.post(f"/api/rooms/{code}/join", json={"player_name": "Youssef"})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["player_color"] == "black"
        assert d2["room_status"] == "active"

        # Third player rejected with 409 room_full
        r3 = client.post(f"/api/rooms/{code}/join", json={"player_name": "Third"})
        assert r3.status_code == 409
        assert r3.json()["error"]["code"] == "room_full"

        # Public GET endpoint never leaks player tokens
        pub = client.get(f"/api/rooms/{code}")
        assert pub.status_code == 200
        raw_text = pub.text
        assert d1["player_token"] not in raw_text
        assert d2["player_token"] not in raw_text


def test_websocket_auth_rejects_missing_or_wrong_token():
    app = create_app()
    with TestClient(app) as client:
        r1 = client.post("/api/rooms", json={"player_name": "Houssam"}).json()
        code = r1["room_code"]

        with client.websocket_connect(f"/ws/{code}?token=wrong-token") as ws:
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["code"] == "unauthorized"


def test_websocket_realtime_moves_validation_disconnect_reconnect_resign_and_rematch():
    app = create_app()
    with TestClient(app) as client:
        p1 = client.post("/api/rooms", json={"player_name": "Houssam"}).json()
        code = p1["room_code"]
        t1 = p1["player_token"]

        with client.websocket_connect(f"/ws/{code}?token={t1}") as ws1:
            init1 = ws1.receive_json()
            assert init1["type"] == "room_state"
            assert init1["room"]["your_color"] == "white"
            assert init1["room"]["game"]["status"] == "waiting"

            # Player 2 joins via REST -> Player 1 receives player_joined immediately
            p2 = client.post(f"/api/rooms/{code}/join", json={"player_name": "Youssef"}).json()
            t2 = p2["player_token"]

            joined_evt = _drain_until_type(ws1, "player_joined")
            assert joined_evt["room"]["game"]["status"] == "active"
            rev = joined_evt["room"]["game"]["revision"]

            with client.websocket_connect(f"/ws/{code}?token={t2}") as ws2:
                init2 = ws2.receive_json()
                assert init2["type"] == "room_state"
                assert init2["room"]["your_color"] == "black"
                # Drain connection status update on ws1
                _drain_until_type(ws1, "room_state")

                # Unknown message type rejected safely
                ws1.send_json({"type": "hack_board"})
                unknown_err = _drain_until_type(ws1, "error")
                assert unknown_err["code"] == "invalid_message"

                # Wrong player turn (Black tries to move first) rejected
                ws2.send_json(
                    {
                        "type": "make_move",
                        "from": [2, 1],
                        "landings": [[3, 0]],
                        "revision": rev,
                    }
                )
                rej_turn = _drain_until_type(ws2, "move_rejected")
                assert rej_turn["code"] == "not_your_turn"

                # White submits valid move -> broadcast once to both players
                ws1.send_json(
                    {
                        "type": "make_move",
                        "from": [5, 0],
                        "landings": [[4, 1]],
                        "revision": rev,
                    }
                )
                m1 = _drain_until_type(ws1, "move_applied")
                m2 = _drain_until_type(ws2, "move_applied")
                assert m1["revision"] == rev + 1
                assert m2["revision"] == rev + 1
                assert m1["move"]["by"] == "white"
                assert m1["move"]["from"] == [5, 0]
                assert m1["move"]["landings"] == [[4, 1]]
                assert m1["room"]["your_color"] == "white"
                assert m2["room"]["your_color"] == "black"

                # Stale revision rejected with latest state returned
                ws2.send_json(
                    {
                        "type": "make_move",
                        "from": [2, 1],
                        "landings": [[3, 0]],
                        "revision": rev,  # stale!
                    }
                )
                rej_stale = _drain_until_type(ws2, "move_rejected")
                assert rej_stale["code"] == "stale_revision"
                assert rej_stale["room"]["game"]["revision"] == rev + 1

            # ws2 closed -> ws1 receives player_disconnected, game remains active
            disc_evt = _drain_until_type(ws1, "player_disconnected")
            assert disc_evt["color"] == "black"
            assert disc_evt["room"]["game"]["status"] == "active"

            # ws2 reconnects with same token -> ws1 receives player_reconnected
            with client.websocket_connect(f"/ws/{code}?token={t2}") as ws2_re:
                re_init = ws2_re.receive_json()
                assert re_init["type"] == "room_state"
                assert re_init["room"]["game"]["revision"] == rev + 1

                reconn_evt = _drain_until_type(ws1, "player_reconnected")
                assert reconn_evt["color"] == "black"

                # Black resigns -> both players receive game_finished
                ws2_re.send_json({"type": "resign"})
                fin1 = _drain_until_type(ws1, "game_finished")
                fin2 = _drain_until_type(ws2_re, "game_finished")
                assert fin1["winner"] == "white"
                assert fin1["finish_reason"] == "resignation"
                assert fin2["winner"] == "white"

                # Mutual rematch: first request updates status without starting
                ws1.send_json({"type": "request_rematch"})
                rem1_a = _drain_until_type(ws1, "rematch_status")
                rem1_b = _drain_until_type(ws2_re, "rematch_status")
                assert rem1_a["started"] is False
                assert rem1_b["started"] is False

                # Second request starts new match and swaps colors
                ws2_re.send_json({"type": "request_rematch"})
                rem2_a = _drain_until_type(ws1, "rematch_status")
                rem2_b = _drain_until_type(ws2_re, "rematch_status")
                assert rem2_a["started"] is True
                assert rem2_b["started"] is True
                assert rem2_a["room"]["game"]["status"] == "active"
                assert rem2_a["room"]["your_color"] == "black"
                assert rem2_b["room"]["your_color"] == "white"


def test_spa_routes_oversized_payload_and_reconnect_race_safety():
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/game/A7K9Q2").status_code == 200

        p1 = client.post("/api/rooms", json={"player_name": "Houssam"}).json()
        p2 = client.post(
            f"/api/rooms/{p1['room_code']}/join", json={"player_name": "Friend"}
        ).json()
        code = p1["room_code"]

        with client.websocket_connect(f"/ws/{code}?token={p1['player_token']}") as ws1_old:
            _drain_until_type(ws1_old, "room_state")

            # Oversized payload rejected cleanly
            ws1_old.send_text("x" * 5000)
            too_big = _drain_until_type(ws1_old, "error")
            assert too_big["code"] == "message_too_large"

            # Open superseding connection for same seat BEFORE old connection closes
            with client.websocket_connect(
                f"/ws/{code}?token={p1['player_token']}"
            ) as ws1_new:
                _drain_until_type(ws1_new, "room_state")

                # Connect opponent and ensure seat 1 is still marked connected after ws1_old closes
                with client.websocket_connect(
                    f"/ws/{code}?token={p2['player_token']}"
                ) as ws2:
                    s2 = _drain_until_type(ws2, "room_state")
                    assert s2["room"]["players"]["white"]["connected"] is True


def test_token_redacting_log_filter_scrubs_sensitive_ws_urls():
    import logging

    from app.main import TokenRedactingFilter

    flt = TokenRedactingFilter()
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='127.0.0.1:5000 - "WebSocket %s" [accepted]',
        args=("/ws/AJCXSQ?token=secret_player_token_123",),
        exc_info=None,
    )
    assert flt.filter(record) is True
    rendered = record.getMessage()
    assert "secret_player_token_123" not in rendered
    assert "token=[REDACTED]" in rendered


def test_websocket_taunt_broadcast_allowlist_and_cooldown():
    app = create_app()
    with TestClient(app) as client:
        p1 = client.post("/api/rooms", json={"player_name": "Houssam"}).json()
        p2 = client.post(
            f"/api/rooms/{p1['room_code']}/join", json={"player_name": "Wiam"}
        ).json()
        code = p1["room_code"]

        with (
            client.websocket_connect(f"/ws/{code}?token={p1['player_token']}") as ws1,
            client.websocket_connect(f"/ws/{code}?token={p2['player_token']}") as ws2,
        ):
            _drain_until_type(ws1, "room_state")
            _drain_until_type(ws2, "room_state")

            # Valid allowlisted Franco-Darija taunt broadcasts to both seats
            ws1.send_json({"type": "send_taunt", "taunt_id": "chreb_atay"})
            t1 = _drain_until_type(ws1, "taunt_sent")
            t2 = _drain_until_type(ws2, "taunt_sent")
            assert t1["taunt_id"] == "chreb_atay"
            assert t1["from_color"] == "white"
            assert t1["sender_name"] == "Houssam"
            assert t2 == t1

            # Immediate second taunt by same player hits anti-spam cooldown
            ws1.send_json({"type": "send_taunt", "taunt_id": "hez_yeddik"})
            cool_err = _drain_until_type(ws1, "error")
            assert cool_err["code"] == "taunt_cooldown"

            # Other player can still taunt independently without being blocked by p1's cooldown
            ws2.send_json({"type": "send_taunt", "taunt_id": "fin_ghadi_7ejra"})
            t2_reply_a = _drain_until_type(ws1, "taunt_sent")
            t2_reply_b = _drain_until_type(ws2, "taunt_sent")
            assert t2_reply_a["taunt_id"] == "fin_ghadi_7ejra"
            assert t2_reply_a["from_color"] == "black"
            assert t2_reply_a["sender_name"] == "Wiam"
            assert t2_reply_b == t2_reply_a

            # Unknown / arbitrary text taunt_id is rejected by strict schema allowlist
            ws2.send_json({"type": "send_taunt", "taunt_id": "<script>alert(1)</script>"})
            bad_err = _drain_until_type(ws2, "error")
            assert bad_err["code"] == "invalid_message"

            # In-game chat broadcast between players
            ws1.send_json({"type": "send_chat", "text": "Salam khoya, rak nadi!"})
            chat1 = _drain_until_type(ws1, "chat_message")
            chat2 = _drain_until_type(ws2, "chat_message")
            assert chat1["text"] == "Salam khoya, rak nadi!"
            assert chat1["sender_name"] == "Houssam"
            assert chat1["from_color"] == "white"
            assert "timestamp" in chat1
            assert chat2 == chat1

            # Opponent replies in chat
            ws2.send_json({"type": "send_chat", "text": "Mer7ba bik, la3ba wa3ra!"})
            rep1 = _drain_until_type(ws1, "chat_message")
            rep2 = _drain_until_type(ws2, "chat_message")
            assert rep1["text"] == "Mer7ba bik, la3ba wa3ra!"
            assert rep1["sender_name"] == "Wiam"
            assert rep1["from_color"] == "black"
            assert rep2 == rep1


def test_disconnect_timeout_closes_room_and_disconnects_opponent():
    import asyncio
    from app.realtime.websocket import ConnectionHub
    from app.rooms.manager import RoomManager

    class FakeWS:
        def __init__(self, name: str) -> None:
            self.name = name
            self.closed = False
            self.close_code = None
            self.messages = []

        async def send_json(self, data: dict) -> None:
            self.messages.append(data)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = True
            self.close_code = code

    async def run() -> None:
        room_mgr = RoomManager(disconnect_grace_seconds=1)
        hub = ConnectionHub()

        r = room_mgr.create_room("Houssam")
        code = r.room_code
        j = room_mgr.join_room(code, "Wiam")

        ws1 = FakeWS("ws1")
        ws2 = FakeWS("ws2")

        await hub.register(code, "seat_1", r.player_token, ws1)
        await hub.register(code, "seat_2", j.player_token, ws2)
        room_mgr.mark_connected(code, r.player_token)
        room_mgr.mark_connected(code, j.player_token)

        # Seat 2 disconnects
        hub.unregister(code, "seat_2", ws2)
        room_mgr.mark_disconnected(code, j.player_token)

        task = hub.schedule_disconnect_timeout(
            room_code=code,
            seat_id="seat_2",
            token=j.player_token,
            seat_name="Wiam",
            timeout_seconds=0.05,
            room_manager=room_mgr,
        )

        assert not task.done()
        await asyncio.sleep(0.1)
        assert task.done()

        # Seat 1 received room_closed and ws1 was closed with code 4410
        assert ws1.closed is True
        assert ws1.close_code == 4410
        assert any(
            m.get("type") == "room_closed" and m.get("reason") == "connection_timeout"
            for m in ws1.messages
        )

        # Room must be removed from RoomManager
        assert code not in room_mgr._rooms

    asyncio.run(run())


def test_reconnect_cancels_disconnect_timeout():
    import asyncio
    from app.realtime.websocket import ConnectionHub
    from app.rooms.manager import RoomManager

    class FakeWS:
        def __init__(self, name: str) -> None:
            self.name = name
            self.closed = False
            self.close_code = None
            self.messages = []

        async def send_json(self, data: dict) -> None:
            self.messages.append(data)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = True
            self.close_code = code

    async def run() -> None:
        room_mgr = RoomManager(disconnect_grace_seconds=1)
        hub = ConnectionHub()

        r = room_mgr.create_room("Houssam")
        code = r.room_code
        j = room_mgr.join_room(code, "Wiam")

        ws1 = FakeWS("ws1")
        ws2 = FakeWS("ws2")

        await hub.register(code, "seat_1", r.player_token, ws1)
        await hub.register(code, "seat_2", j.player_token, ws2)
        room_mgr.mark_connected(code, r.player_token)
        room_mgr.mark_connected(code, j.player_token)

        # Seat 2 disconnects
        hub.unregister(code, "seat_2", ws2)
        room_mgr.mark_disconnected(code, j.player_token)

        task = hub.schedule_disconnect_timeout(
            room_code=code,
            seat_id="seat_2",
            token=j.player_token,
            seat_name="Wiam",
            timeout_seconds=0.2,
            room_manager=room_mgr,
        )

        # Seat 2 reconnects before timeout
        ws2_re = FakeWS("ws2_re")
        await hub.register(code, "seat_2", j.player_token, ws2_re)
        room_mgr.mark_connected(code, j.player_token)

        # Timer task should have been cancelled by register
        await asyncio.sleep(0.01)
        assert task.cancelled()

        await asyncio.sleep(0.25)
        # Verify ws1 was NOT closed and room remains active
        assert ws1.closed is False
        assert code in room_mgr._rooms
        assert room_mgr.get_public_snapshot(code).game.status == "active"

    asyncio.run(run())

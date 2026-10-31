from app.game.config import RulesConfig
from app.game.engine import apply_move, create_custom_game_state
from app.game.models import MoveAttempt


def test_man_promotes_on_reaching_far_row_by_normal_move():
    state = create_custom_game_state(
        pieces={
            (1, 2): ("white", "man"),
            (6, 5): ("black", "man"),
        },
        current_turn="white",
    )
    state_after_white = apply_move(state, MoveAttempt(**{"from": (1, 2), "landings": [(0, 3)]}))
    crowned_white = state_after_white.board[0][3]
    assert crowned_white is not None
    assert crowned_white.rank == "king"
    assert state_after_white.last_move is not None
    assert state_after_white.last_move.promoted is True

    state_after_black = apply_move(
        state_after_white, MoveAttempt(**{"from": (6, 5), "landings": [(7, 4)]})
    )
    crowned_black = state_after_black.board[7][4]
    assert crowned_black is not None
    assert crowned_black.rank == "king"
    assert state_after_black.last_move is not None
    assert state_after_black.last_move.promoted is True


def test_promotion_during_capture_stops_turn_by_default():
    # White man at (2, 1) jumps (1, 2) onto promotion row (0, 3).
    # Another black piece sits at (1, 4) with (2, 5) empty.
    # In initial Moroccan Dama profile (promote_mid_capture_stops_turn=True),
    # the man crowns at (0, 3) and MUST stop rather than continuing backward as a king.
    pieces = {
        (2, 1): ("white", "man"),
        (1, 2): ("black", "man"),
        (1, 4): ("black", "man"),
        (7, 0): ("black", "man"),
    }
    state_default = create_custom_game_state(
        pieces=pieces,
        current_turn="white",
        config=RulesConfig(promote_mid_capture_stops_turn=True),
    )
    assert len(state_default.legal_moves) == 1
    assert state_default.legal_moves[0].landings == [(0, 3)]
    assert state_default.legal_moves[0].captured == [(1, 2)]

    next_state = apply_move(
        state_default, MoveAttempt(**{"from": (2, 1), "landings": [(0, 3)]})
    )
    assert next_state.board[0][3] is not None
    assert next_state.board[0][3].rank == "king"
    assert next_state.board[1][4] is not None  # untouched


def test_promotion_during_capture_continues_when_configured():
    pieces = {
        (2, 1): ("white", "man"),
        (1, 2): ("black", "man"),
        (1, 4): ("black", "man"),
        (7, 0): ("black", "man"),
    }
    state_continue = create_custom_game_state(
        pieces=pieces,
        current_turn="white",
        config=RulesConfig(promote_mid_capture_stops_turn=False),
    )
    # Now crowning mid-sequence continues as a flying king jumping (1, 4) to (2, 5), (3, 6), (4, 7)
    assert all(len(m.captured) == 2 for m in state_continue.legal_moves)
    landings = {tuple(m.landings) for m in state_continue.legal_moves}
    assert landings == {((0, 3), (2, 5)), ((0, 3), (3, 6)), ((0, 3), (4, 7))}

    next_state = apply_move(
        state_continue, MoveAttempt(**{"from": (2, 1), "landings": [(0, 3), (2, 5)]})
    )
    assert next_state.board[2][5] is not None
    assert next_state.board[2][5].rank == "king"
    assert next_state.captured["black"] == 2

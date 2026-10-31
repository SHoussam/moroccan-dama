import pytest

from app.game.config import RulesConfig
from app.game.engine import IllegalMoveError, apply_move, create_custom_game_state
from app.game.models import Color, Coord, MoveAttempt, Rank
from app.game.rules import get_legal_moves


def test_man_forward_capture_and_mandatory_capture_enforcement():
    state = create_custom_game_state(
        pieces={
            (5, 0): ("white", "man"),
            (4, 1): ("black", "man"),
            (5, 6): ("white", "man"),  # has a quiet move to (4, 5)/(4, 7), which must be forbidden
            (0, 7): ("black", "man"),
        },
        current_turn="white",
    )
    assert state.mandatory_capture is True
    moves = get_legal_moves(state.board, "white", state.rules_config)
    assert len(moves) == 1
    assert moves[0].from_pos == (5, 0)
    assert moves[0].landings == [(3, 2)]
    assert moves[0].captured == [(4, 1)]
    assert moves[0].is_capture is True

    # Quiet move with the other piece must fail with mandatory_capture
    with pytest.raises(IllegalMoveError) as exc_info:
        apply_move(state, MoveAttempt(**{"from": (5, 6), "landings": [(4, 5)]}))
    assert exc_info.value.code == "mandatory_capture"

    # Applying the mandatory capture removes (4, 1) and increments captured["black"]
    next_state = apply_move(state, MoveAttempt(**{"from": (5, 0), "landings": [(3, 2)]}))
    assert next_state.board[5][0] is None
    assert next_state.board[4][1] is None
    assert next_state.board[3][2] is not None
    assert next_state.board[3][2].color == "white"
    assert next_state.captured["black"] == 1
    assert next_state.captured["white"] == 0


def test_man_cannot_capture_backward():
    state = create_custom_game_state(
        pieces={
            (3, 2): ("white", "man"),
            (4, 3): ("black", "man"),  # behind white man; (5, 4) is empty
        },
        current_turn="white",
    )
    moves = get_legal_moves(state.board, "white", state.rules_config)
    assert all(not m.is_capture for m in moves)
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (3, 2), "landings": [(5, 4)]}))


def test_man_can_capture_enemy_king_forward():
    state = create_custom_game_state(
        pieces={
            (5, 2): ("white", "man"),
            (4, 3): ("black", "king"),
            (0, 1): ("black", "man"),
        },
        current_turn="white",
    )
    next_state = apply_move(state, MoveAttempt(**{"from": (5, 2), "landings": [(3, 4)]}))
    assert next_state.board[4][3] is None
    assert next_state.captured["black"] == 1


def test_multi_capture_must_complete_full_sequence():
    # README example: (5, 0) -> (3, 2) -> (1, 4) jumping (4, 1) and (2, 3)
    state = create_custom_game_state(
        pieces={
            (5, 0): ("white", "man"),
            (4, 1): ("black", "man"),
            (2, 3): ("black", "man"),
            (0, 7): ("black", "man"),
        },
        current_turn="white",
    )
    moves = get_legal_moves(state.board, "white", state.rules_config)
    assert len(moves) == 1
    assert moves[0].from_pos == (5, 0)
    assert moves[0].landings == [(3, 2), (1, 4)]
    assert moves[0].captured == [(4, 1), (2, 3)]

    # Stopping early after the first jump must be rejected
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (5, 0), "landings": [(3, 2)]}))

    # Full sequence succeeds and removes both pieces
    next_state = apply_move(state, MoveAttempt(**{"from": (5, 0), "landings": [(3, 2), (1, 4)]}))
    assert next_state.board[4][1] is None
    assert next_state.board[2][3] is None
    assert next_state.board[1][4] is not None
    assert next_state.captured["black"] == 2


def test_maximum_capture_rejects_shorter_sequence():
    # Case 1: Across two pieces
    # Piece A at (5, 0) can capture 2 pieces: (4, 1) and (2, 3) -> lands (1, 4)
    # Piece B at (7, 6) can capture only 1 piece: (6, 5) -> lands (5, 4)
    state = create_custom_game_state(
        pieces={
            (5, 0): ("white", "man"),
            (4, 1): ("black", "man"),
            (2, 3): ("black", "man"),
            (7, 6): ("white", "man"),
            (6, 5): ("black", "man"),
            (0, 7): ("black", "man"),
        },
        current_turn="white",
    )
    moves = get_legal_moves(state.board, "white", state.rules_config)
    assert len(moves) == 1
    assert moves[0].from_pos == (5, 0)
    assert moves[0].landings == [(3, 2), (1, 4)]

    # Attempting the 1-piece capture when a 2-piece capture exists is rejected
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (7, 6), "landings": [(5, 4)]}))

    # Case 2: Same piece branching into 1-capture left vs 2-capture right
    branch_state = create_custom_game_state(
        pieces={
            (5, 2): ("white", "man"),
            (4, 1): ("black", "man"),  # left branch: 1 capture -> (3, 0)
            (4, 3): ("black", "man"),  # right branch: (3, 4) -> jumps (2, 5) -> (1, 6)
            (2, 5): ("black", "man"),
            (0, 7): ("black", "man"),
        },
        current_turn="white",
    )
    branch_moves = get_legal_moves(branch_state.board, "white", branch_state.rules_config)
    assert len(branch_moves) == 1
    assert branch_moves[0].landings == [(3, 4), (1, 6)]
    with pytest.raises(IllegalMoveError):
        apply_move(branch_state, MoveAttempt(**{"from": (5, 2), "landings": [(3, 0)]}))


def test_equal_capture_tiebreak_none_vs_prefer_kings():
    # White man at (5, 2) can jump left over a black man at (4, 1) -> (3, 0)
    # OR jump right over a black king at (4, 3) -> (3, 4)
    pieces: dict[Coord, tuple[Color, Rank]] = {
        (5, 2): ("white", "man"),
        (4, 1): ("black", "man"),
        (4, 3): ("black", "king"),
        (0, 7): ("black", "man"),
    }

    # Initial profile: tiebreak="none" -> both 1-capture sequences are legal
    state_none = create_custom_game_state(
        pieces=pieces,
        current_turn="white",
        config=RulesConfig(equal_capture_tiebreak="none"),
    )
    landings_none = {tuple(m.landings) for m in state_none.legal_moves}
    assert landings_none == {((3, 0),), ((3, 4),)}

    # Optional profile: tiebreak="prefer_kings" -> must capture the king at (4, 3)
    state_prefer = create_custom_game_state(
        pieces=pieces,
        current_turn="white",
        config=RulesConfig(equal_capture_tiebreak="prefer_kings"),
    )
    landings_prefer = {tuple(m.landings) for m in state_prefer.legal_moves}
    assert landings_prefer == {((3, 4),)}

import pytest

from app.game.engine import (
    IllegalMoveError,
    apply_move,
    create_custom_game_state,
    create_initial_game_state,
)
from app.game.models import MoveAttempt
from app.game.rules import get_legal_moves


def test_white_man_moves_diagonally_forward():
    state = create_custom_game_state(
        pieces={
            (5, 2): ("white", "man"),
            (0, 1): ("black", "man"),
        },
        current_turn="white",
    )
    moves = get_legal_moves(state.board, "white", state.rules_config)
    destinations = {tuple(m.landings) for m in moves if m.from_pos == (5, 2)}
    assert destinations == {((4, 1),), ((4, 3),)}

    next_state = apply_move(state, MoveAttempt(**{"from": (5, 2), "landings": [(4, 3)]}))
    assert next_state.board[5][2] is None
    assert next_state.board[4][3] is not None
    assert next_state.board[4][3].color == "white"
    assert next_state.current_turn == "black"
    assert next_state.revision == state.revision + 1
    assert next_state.move_number == state.move_number + 1
    # Original state must not be mutated
    assert state.board[5][2] is not None
    assert state.board[4][3] is None


def test_black_man_moves_diagonally_forward_downward():
    state = create_custom_game_state(
        pieces={
            (2, 3): ("black", "man"),
            (7, 0): ("white", "man"),
        },
        current_turn="black",
    )
    moves = get_legal_moves(state.board, "black", state.rules_config)
    destinations = {tuple(m.landings) for m in moves if m.from_pos == (2, 3)}
    assert destinations == {((3, 2),), ((3, 4),)}


def test_man_cannot_move_backward_or_into_occupied_square():
    state = create_custom_game_state(
        pieces={
            (4, 3): ("white", "man"),
            (3, 2): ("white", "man"),  # friendly blocker forward-left
            (0, 1): ("black", "man"),
        },
        current_turn="white",
    )
    moves = get_legal_moves(state.board, "white", state.rules_config)
    from_4_3 = {tuple(m.landings) for m in moves if m.from_pos == (4, 3)}
    # Only forward-right (3, 4) is open; backward (5, 2) and (5, 4) are illegal
    assert from_4_3 == {((3, 4),)}

    # Attempting backward move raises IllegalMoveError and leaves state unchanged
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (4, 3), "landings": [(5, 2)]}))

    # Attempting move into occupied square fails
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (4, 3), "landings": [(3, 2)]}))

    assert state.board[4][3] is not None
    assert state.revision == 0


def test_wrong_turn_and_malformed_coordinates_rejected():
    state = create_initial_game_state()
    # Black tries to move on White's turn
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (2, 1), "landings": [(3, 0)]}))

    # Out-of-bounds coordinates rejected
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (5, 0), "landings": [(4, -1)]}))

    # Non-playable light square rejected
    with pytest.raises(IllegalMoveError):
        apply_move(state, MoveAttempt(**{"from": (5, 0), "landings": [(4, 0)]}))

    assert state.revision == 0

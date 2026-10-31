import pytest

from app.game.engine import IllegalMoveError, apply_move, create_custom_game_state, resign_game
from app.game.models import MoveAttempt


def test_win_when_last_opponent_piece_captured():
    state = create_custom_game_state(
        pieces={
            (5, 2): ("white", "man"),
            (4, 3): ("black", "man"),
        },
        current_turn="white",
    )
    final_state = apply_move(state, MoveAttempt(**{"from": (5, 2), "landings": [(3, 4)]}))
    assert final_state.status == "finished"
    assert final_state.winner == "white"
    assert final_state.finish_reason == "no_pieces"
    assert final_state.legal_moves == []

    # Further moves after game finished are rejected
    with pytest.raises(IllegalMoveError):
        apply_move(final_state, MoveAttempt(**{"from": (3, 4), "landings": [(2, 3)]}))


def test_win_when_opponent_has_no_legal_moves():
    # Black has one man at (6, 1) Moving downward to row 7:
    # (7, 0) is occupied by white king or friendly blocker? Wait: if (7, 0) and (7, 2) are blocked:
    # Put Black man at (5, 0) moving down to (6, 1), and White man at (7, 2) moves to (6, 1) blocking Black!
    # Wait: if White moves (7, 2) -> (6, 1), can Black jump (6, 1) to (7, 2)?
    # Not if (7, 2) is ALSO occupied by another White piece!
    state = create_custom_game_state(
        pieces={
            (5, 0): ("black", "man"),
            (7, 0): ("white", "man"),  # moves to (6, 1)
            (7, 2): ("white", "man"),  # blocks landing at (7, 2) so Black cannot jump (6, 1)!
        },
        current_turn="white",
    )
    final_state = apply_move(state, MoveAttempt(**{"from": (7, 0), "landings": [(6, 1)]}))
    assert final_state.status == "finished"
    assert final_state.winner == "white"
    assert final_state.finish_reason == "no_legal_moves"
    assert final_state.legal_moves == []


def test_resignation_awards_win_to_opponent():
    state = create_custom_game_state(
        pieces={
            (5, 0): ("white", "man"),
            (2, 3): ("black", "man"),
        },
        current_turn="white",
    )
    resigned = resign_game(state, "white")
    assert resigned.status == "finished"
    assert resigned.winner == "black"
    assert resigned.finish_reason == "resignation"
    assert resigned.revision == state.revision + 1

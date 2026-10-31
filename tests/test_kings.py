import pytest

from app.game.config import RulesConfig
from app.game.engine import IllegalMoveError, apply_move, create_custom_game_state
from app.game.models import MoveAttempt
from app.game.rules import get_legal_moves


def test_flying_king_long_range_moves_and_friendly_blocker():
    state = create_custom_game_state(
        pieces={
            (4, 3): ("white", "king"),
            (2, 1): ("white", "man"),  # friendly blocker on NW diagonal
            (0, 7): ("black", "man"),  # enemy at corner
        },
        current_turn="white",
    )
    moves = get_legal_moves(state.board, "white", state.rules_config)
    king_landings = {m.landings[0] for m in moves if m.from_pos == (4, 3)}

    # NW stops before (2, 1) -> only (3, 2)
    assert (3, 2) in king_landings
    assert (2, 1) not in king_landings
    assert (1, 0) not in king_landings

    # NE reaches (3, 4), (2, 5), (1, 6), stops before enemy at (0, 7)
    assert {(3, 4), (2, 5), (1, 6)}.issubset(king_landings)
    assert (0, 7) not in king_landings

    # SW reaches (5, 2), (6, 1), (7, 0)
    assert {(5, 2), (6, 1), (7, 0)}.issubset(king_landings)

    # SE reaches (5, 4), (6, 5), (7, 6)
    assert {(5, 4), (6, 5), (7, 6)}.issubset(king_landings)


def test_flying_king_capture_any_empty_square_beyond_and_blocker():
    state = create_custom_game_state(
        pieces={
            (7, 0): ("white", "king"),
            (4, 3): ("black", "man"),
            (1, 6): ("black", "man"),  # second enemy further along same diagonal blocks behind (2, 5)
        },
        current_turn="white",
    )
    # From (7, 0), king jumps (4, 3). Empty squares before (1, 6) are (3, 4) and (2, 5).
    #Wait: from (3, 4) or (2, 5), can it jump (1, 6) to (0, 7)? YES! (0, 7) is empty!
    # So maximum capture forces jumping BOTH (4, 3) and (1, 6) to land on (0, 7)!
    moves = get_legal_moves(state.board, "white", state.rules_config)
    assert all(len(m.captured) == 2 for m in moves)
    paths = {tuple(m.landings) for m in moves}
    assert paths == {((3, 4), (0, 7)), ((2, 5), (0, 7))}


def test_flying_king_single_capture_multiple_landing_choices_and_adjacent_config():
    pieces = {
        (7, 0): ("white", "king"),
        (5, 2): ("black", "man"),
        (1, 6): ("white", "man"),  # friendly piece blocks at (1, 6)
        (0, 1): ("black", "man"),
    }
    state_flying = create_custom_game_state(
        pieces=pieces,
        current_turn="white",
        config=RulesConfig(king_capture_landing="any_beyond"),
    )
    landings_flying = {tuple(m.landings) for m in state_flying.legal_moves}
    assert landings_flying == {((4, 3),), ((3, 4),), ((2, 5),)}

    state_adj = create_custom_game_state(
        pieces=pieces,
        current_turn="white",
        config=RulesConfig(king_capture_landing="adjacent_only"),
    )
    landings_adj = {tuple(m.landings) for m in state_adj.legal_moves}
    assert landings_adj == {((4, 3),)}


def test_king_cannot_jump_two_adjacent_enemies_or_capture_same_piece_twice():
    # Two adjacent black pieces at (4, 3) and (3, 4) block each other along the diagonal
    state_blocked = create_custom_game_state(
        pieces={
            (6, 1): ("white", "king"),
            (4, 3): ("black", "man"),
            (3, 4): ("black", "man"),
        },
        current_turn="white",
    )
    assert state_blocked.mandatory_capture is False
    assert all(not m.is_capture for m in state_blocked.legal_moves)

    # Diamond loop where king could revisit the diagonal of an already-captured piece:
    # White king at (5, 2), enemies at (4, 3), (2, 5), (2, 3), (4, 1) — wait:
    # Let's construct a Turkish-strike ("coup turc") position where jumping (4, 3) -> (3, 4),
    # then (2, 3) -> (1, 2), then (2, 1) -> (3, 0) or trying to re-jump/pass through (4, 3):
    # Specifically: king at (6, 1), enemies at (4, 3), (2, 3), (2, 1), (4, 1)?
    # Check parity: (6,1)=7, (4,3)=7, (3,4)=7, (2,3)=5, (1,2)=3, (2,1)=3, (3,0)=3. All odd!
    # Let's test Turkish strike directly:
    # King at (5, 0) [sum 5]:
    # Jump 1: enemy at (4, 1) -> lands (2, 3)
    # Jump 2: enemy at (3, 4) -> lands (4, 5)
    # Jump 3: enemy at (5, 4) -> lands (6, 3)
    # Jump 4: enemy at (5, 2) -> lands (4, 1)? NO! (4, 1) still holds the captured piece from Jump 1!
    # Nor can it slide through (4, 1) to (3, 0)! It CAN land on (3, 0) ONLY if (4, 1) weren't there,
    # so with captured_pieces_block_during_sequence=True, Jump 4 cannot land on or pass through (4, 1)!
    state_turkish = create_custom_game_state(
        pieces={
            (5, 0): ("white", "king"),
            (4, 1): ("black", "man"),
            (3, 4): ("black", "man"),
            (5, 4): ("black", "man"),
            (5, 2): ("black", "man"),
        },
        current_turn="white",
    )
    moves = get_legal_moves(state_turkish.board, "white", state_turkish.rules_config)
    for m in moves:
        # Never captures the same coordinate twice
        assert len(m.captured) == len(set(m.captured))
        # Cannot land on (4, 1) or pass through (4, 1) to (3, 0) while (4, 1) is an unremoved hurdle
        if m.captured and m.captured[0] == (4, 1):
            assert (4, 1) not in m.landings
            assert (3, 0) not in m.landings

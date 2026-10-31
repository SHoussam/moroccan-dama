from app.game.config import DEFAULT_RULES_CONFIG, RulesConfig
from app.game.models import (
    Color,
    Coord,
    FinishReason,
    GameState,
    GameStatus,
    LastMoveInfo,
    MoveAttempt,
    Piece,
    Rank,
    is_playable_square,
    opponent_of,
    promotion_row,
)
from app.game.rules import get_legal_moves


class IllegalMoveError(ValueError):
    """Raised when an attempted move or game action violates Moroccan Dama rules."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def create_empty_board(board_size: int = 8) -> list[list[Piece | None]]:
    """Create an empty board_size x board_size grid."""
    return [[None for _ in range(board_size)] for _ in range(board_size)]


def clone_board(board: list[list[Piece | None]]) -> list[list[Piece | None]]:
    """Return a shallow-row copy of the board (Piece objects are frozen/immutable)."""
    return [list(row) for row in board]


def create_initial_board(
    config: RulesConfig = DEFAULT_RULES_CONFIG,
) -> list[list[Piece | None]]:
    """Create the initial Moroccan Dama 8x8 board with 12 men per side."""
    size = config.board_size
    board = create_empty_board(size)
    black_idx = 1
    white_idx = 1

    for r in range(3):
        for c in range(size):
            if is_playable_square(r, c, size):
                board[r][c] = Piece(id=f"b{black_idx}", color="black", rank="man")
                black_idx += 1

    for r in range(size - 3, size):
        for c in range(size):
            if is_playable_square(r, c, size):
                board[r][c] = Piece(id=f"w{white_idx}", color="white", rank="man")
                white_idx += 1

    return board


def create_initial_game_state(
    config: RulesConfig = DEFAULT_RULES_CONFIG,
    status: GameStatus = "active",
) -> GameState:
    """Create a fresh Moroccan Dama game state."""
    board = create_initial_board(config)
    legal = get_legal_moves(board, "white", config) if status == "active" else []
    mandatory = any(m.is_capture for m in legal)
    return GameState(
        board=board,
        current_turn="white",
        status=status,
        winner=None,
        finish_reason=None,
        captured={"white": 0, "black": 0},
        move_number=0,
        revision=0,
        last_move=None,
        rules_config=config,
        legal_moves=legal,
        mandatory_capture=mandatory,
    )


def create_custom_game_state(
    pieces: dict[Coord, tuple[Color, Rank] | Piece],
    current_turn: Color = "white",
    config: RulesConfig = DEFAULT_RULES_CONFIG,
    status: GameStatus = "active",
    revision: int = 0,
    move_number: int = 0,
    captured: dict[Color, int] | None = None,
) -> GameState:
    """Create an explicit board fixture for unit and integration testing."""
    size = config.board_size
    board = create_empty_board(size)
    counters: dict[Color, int] = {"white": 1, "black": 1}

    for (r, c), spec in pieces.items():
        if not is_playable_square(r, c, size):
            raise ValueError(f"Coordinate ({r}, {c}) is not a valid playable dark square.")
        if isinstance(spec, Piece):
            board[r][c] = spec
        else:
            p_color, p_rank = spec
            prefix = "w" if p_color == "white" else "b"
            pid = f"{prefix}{counters[p_color]}"
            counters[p_color] += 1
            board[r][c] = Piece(id=pid, color=p_color, rank="king" if p_rank == "king" else "man")

    legal = get_legal_moves(board, current_turn, config) if status == "active" else []
    mandatory = any(m.is_capture for m in legal)
    return GameState(
        board=board,
        current_turn=current_turn,
        status=status,
        winner=None,
        finish_reason=None,
        captured=dict(captured) if captured is not None else {"white": 0, "black": 0},
        move_number=move_number,
        revision=revision,
        last_move=None,
        rules_config=config,
        legal_moves=legal,
        mandatory_capture=mandatory,
    )


def count_pieces(board: list[list[Piece | None]], color: Color) -> int:
    """Count remaining pieces on the board for `color`."""
    return sum(
        1 for row in board for piece in row if piece is not None and piece.color == color
    )


def activate_game_state(state: GameState) -> GameState:
    """Transition a waiting game state to active and populate legal moves."""
    board = clone_board(state.board)
    legal = get_legal_moves(board, state.current_turn, state.rules_config)
    return GameState(
        board=board,
        current_turn=state.current_turn,
        status="active",
        winner=None,
        finish_reason=None,
        captured=dict(state.captured),
        move_number=state.move_number,
        revision=state.revision + 1,
        last_move=state.last_move,
        rules_config=state.rules_config,
        legal_moves=legal,
        mandatory_capture=any(m.is_capture for m in legal),
    )


def apply_move(state: GameState, move: MoveAttempt) -> GameState:
    """Validate and commit a complete turn, returning a new authoritative GameState."""
    if state.status != "active":
        raise IllegalMoveError("game_not_active", "The match is not currently active.")

    config = state.rules_config
    size = config.board_size
    from_r, from_c = move.from_pos

    if not is_playable_square(from_r, from_c, size):
        raise IllegalMoveError(
            "invalid_coordinates", "Origin square is outside playable dark squares."
        )

    if not move.landings:
        raise IllegalMoveError(
            "invalid_move_format", "Move must contain at least one landing square."
        )

    for lr, lc in move.landings:
        if not is_playable_square(lr, lc, size):
            raise IllegalMoveError(
                "invalid_coordinates", "Landing square is outside playable dark squares."
            )

    piece = state.board[from_r][from_c]
    if piece is None:
        raise IllegalMoveError("empty_origin", "No piece exists on the selected square.")

    if piece.color != state.current_turn:
        raise IllegalMoveError("wrong_piece_color", "You can only move your own pieces.")

    legal_moves = get_legal_moves(state.board, state.current_turn, config)
    matched = next(
        (
            lm
            for lm in legal_moves
            if lm.from_pos == move.from_pos and lm.landings == move.landings
        ),
        None,
    )

    if matched is None:
        has_captures = any(lm.is_capture for lm in legal_moves)
        if has_captures:
            # Distinguish trying a quiet move when capture is mandatory vs incomplete/non-maximal capture
            dr = abs(move.landings[0][0] - from_r)
            if len(move.landings) == 1 and dr == 1:
                raise IllegalMoveError(
                    "mandatory_capture",
                    "A capture is available and mandatory in Moroccan Dama.",
                )
            raise IllegalMoveError(
                "invalid_capture_sequence",
                "You must complete a legal maximum-capture sequence.",
            )
        raise IllegalMoveError("illegal_move", "That move is not legal.")

    new_board = clone_board(state.board)
    new_board[from_r][from_c] = None

    opp_color = opponent_of(state.current_turn)
    new_captured = dict(state.captured)
    for cap_r, cap_c in matched.captured:
        new_board[cap_r][cap_c] = None
        new_captured[opp_color] = new_captured.get(opp_color, 0) + 1

    final_r, final_c = matched.landings[-1]
    promo_r = promotion_row(piece.color, size)
    promoted = piece.rank == "man" and any(lr == promo_r for lr, _ in matched.landings)
    placed_piece = (
        Piece(id=piece.id, color=piece.color, rank="king") if promoted else piece
    )
    new_board[final_r][final_c] = placed_piece

    last_move = LastMoveInfo(
        by=state.current_turn,
        piece_id=piece.id,
        from_pos=matched.from_pos,
        landings=list(matched.landings),
        captured=list(matched.captured),
        promoted=promoted,
    )

    remaining_opp = count_pieces(new_board, opp_color)
    if remaining_opp == 0:
        return GameState(
            board=new_board,
            current_turn=opp_color,
            status="finished",
            winner=state.current_turn,
            finish_reason="no_pieces",
            captured=new_captured,
            move_number=state.move_number + 1,
            revision=state.revision + 1,
            last_move=last_move,
            rules_config=config,
            legal_moves=[],
            mandatory_capture=False,
        )

    next_legal = get_legal_moves(new_board, opp_color, config)
    if not next_legal:
        return GameState(
            board=new_board,
            current_turn=opp_color,
            status="finished",
            winner=state.current_turn,
            finish_reason="no_legal_moves",
            captured=new_captured,
            move_number=state.move_number + 1,
            revision=state.revision + 1,
            last_move=last_move,
            rules_config=config,
            legal_moves=[],
            mandatory_capture=False,
        )

    return GameState(
        board=new_board,
        current_turn=opp_color,
        status="active",
        winner=None,
        finish_reason=None,
        captured=new_captured,
        move_number=state.move_number + 1,
        revision=state.revision + 1,
        last_move=last_move,
        rules_config=config,
        legal_moves=next_legal,
        mandatory_capture=any(m.is_capture for m in next_legal),
    )


def resign_game(state: GameState, resigning_color: Color) -> GameState:
    """Resign on behalf of `resigning_color`, awarding victory to the opponent."""
    if state.status != "active":
        raise IllegalMoveError("game_not_active", "Cannot resign when match is not active.")

    winner: Color = opponent_of(resigning_color)
    reason: FinishReason = "resignation"
    return GameState(
        board=clone_board(state.board),
        current_turn=state.current_turn,
        status="finished",
        winner=winner,
        finish_reason=reason,
        captured=dict(state.captured),
        move_number=state.move_number,
        revision=state.revision + 1,
        last_move=state.last_move,
        rules_config=state.rules_config,
        legal_moves=[],
        mandatory_capture=False,
    )

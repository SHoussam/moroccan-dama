from typing import Literal

from app.game.config import DEFAULT_RULES_CONFIG, RulesConfig
from app.game.models import (
    Color,
    Coord,
    LegalMove,
    Piece,
    Rank,
    forward_row_delta,
    is_in_bounds,
    is_playable_square,
    promotion_row,
)

ALL_DIAGONALS: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
)

SquareOccupancy = Literal["empty", "blocker", "capturable"]


def _square_occupancy(
    board: list[list[Piece | None]],
    row: int,
    col: int,
    moving_color: Color,
    start_pos: Coord,
    captured_set: frozenset[Coord],
    config: RulesConfig,
) -> SquareOccupancy:
    if (row, col) == start_pos:
        return "empty"
    piece = board[row][col]
    if piece is None:
        return "empty"
    if (row, col) in captured_set:
        return "blocker" if config.captured_pieces_block_during_sequence else "empty"
    if piece.color == moving_color:
        return "blocker"
    return "capturable"


def _generate_man_captures(
    board: list[list[Piece | None]],
    moving_color: Color,
    start_pos: Coord,
    cur_pos: Coord,
    landings_so_far: list[Coord],
    captured_so_far: list[Coord],
    captured_set: frozenset[Coord],
    config: RulesConfig,
) -> list[tuple[list[Coord], list[Coord]]]:
    dr = forward_row_delta(moving_color)
    promo_r = promotion_row(moving_color, config.board_size)
    cur_r, cur_c = cur_pos
    results: list[tuple[list[Coord], list[Coord]]] = []
    found_jump = False

    for dc in (-1, 1):
        mid_r, mid_c = cur_r + dr, cur_c + dc
        land_r, land_c = cur_r + 2 * dr, cur_c + 2 * dc
        if not is_in_bounds(land_r, land_c, config.board_size):
            continue

        mid_occ = _square_occupancy(
            board, mid_r, mid_c, moving_color, start_pos, captured_set, config
        )
        land_occ = _square_occupancy(
            board, land_r, land_c, moving_color, start_pos, captured_set, config
        )
        if mid_occ != "capturable" or land_occ != "empty":
            continue

        found_jump = True
        next_landings = [*landings_so_far, (land_r, land_c)]
        next_captured = [*captured_so_far, (mid_r, mid_c)]
        next_captured_set = captured_set | {(mid_r, mid_c)}

        if land_r == promo_r:
            if config.promote_mid_capture_stops_turn:
                results.append((next_landings, next_captured))
            else:
                results.extend(
                    _generate_king_captures(
                        board=board,
                        moving_color=moving_color,
                        start_pos=start_pos,
                        cur_pos=(land_r, land_c),
                        landings_so_far=next_landings,
                        captured_so_far=next_captured,
                        captured_set=next_captured_set,
                        config=config,
                    )
                )
        else:
            results.extend(
                _generate_man_captures(
                    board=board,
                    moving_color=moving_color,
                    start_pos=start_pos,
                    cur_pos=(land_r, land_c),
                    landings_so_far=next_landings,
                    captured_so_far=next_captured,
                    captured_set=next_captured_set,
                    config=config,
                )
            )

    if not found_jump and landings_so_far:
        results.append((landings_so_far, captured_so_far))

    return results


def _generate_king_captures(
    board: list[list[Piece | None]],
    moving_color: Color,
    start_pos: Coord,
    cur_pos: Coord,
    landings_so_far: list[Coord],
    captured_so_far: list[Coord],
    captured_set: frozenset[Coord],
    config: RulesConfig,
) -> list[tuple[list[Coord], list[Coord]]]:
    cur_r, cur_c = cur_pos
    size = config.board_size
    results: list[tuple[list[Coord], list[Coord]]] = []
    found_any_jump = False

    for dr, dc in ALL_DIAGONALS:
        step = 1
        enemy_pos: Coord | None = None
        while True:
            if not config.king_flying_moves and step > 1:
                break
            r = cur_r + step * dr
            c = cur_c + step * dc
            if not is_in_bounds(r, c, size):
                break
            occ = _square_occupancy(
                board, r, c, moving_color, start_pos, captured_set, config
            )
            if occ == "empty":
                step += 1
                continue
            if occ == "blocker":
                break
            enemy_pos = (r, c)
            break

        if enemy_pos is None:
            continue

        enemy_r, enemy_c = enemy_pos
        candidate_landings: list[Coord] = []
        after_step = 1
        while True:
            if config.king_capture_landing == "adjacent_only" and after_step > 1:
                break
            land_r = enemy_r + after_step * dr
            land_c = enemy_c + after_step * dc
            if not is_in_bounds(land_r, land_c, size):
                break
            land_occ = _square_occupancy(
                board, land_r, land_c, moving_color, start_pos, captured_set, config
            )
            if land_occ != "empty":
                break
            candidate_landings.append((land_r, land_c))
            after_step += 1

        if not candidate_landings:
            continue

        found_any_jump = True
        next_captured = [*captured_so_far, enemy_pos]
        next_captured_set = captured_set | {enemy_pos}

        continuations_for_enemy: list[tuple[list[Coord], list[Coord]]] = []
        dead_ends_for_enemy: list[tuple[list[Coord], list[Coord]]] = []

        for land_pos in candidate_landings:
            next_landings = [*landings_so_far, land_pos]
            sub_sequences = _generate_king_captures(
                board=board,
                moving_color=moving_color,
                start_pos=start_pos,
                cur_pos=land_pos,
                landings_so_far=next_landings,
                captured_so_far=next_captured,
                captured_set=next_captured_set,
                config=config,
            )
            for seq_landings, seq_captured in sub_sequences:
                if len(seq_captured) > len(next_captured):
                    continuations_for_enemy.append((seq_landings, seq_captured))
                else:
                    dead_ends_for_enemy.append((seq_landings, seq_captured))

        if continuations_for_enemy:
            results.extend(continuations_for_enemy)
        else:
            results.extend(dead_ends_for_enemy)

    if not found_any_jump and landings_so_far:
        results.append((landings_so_far, captured_so_far))

    return results


def _generate_quiet_moves_for_piece(
    board: list[list[Piece | None]],
    pos: Coord,
    piece: Piece,
    config: RulesConfig,
) -> list[LegalMove]:
    r, c = pos
    size = config.board_size
    moves: list[LegalMove] = []

    if piece.rank == "man":
        dr = forward_row_delta(piece.color)
        for dc in (-1, 1):
            nr, nc = r + dr, c + dc
            if is_playable_square(nr, nc, size) and board[nr][nc] is None:
                moves.append(
                    LegalMove(
                        from_pos=pos,
                        landings=[(nr, nc)],
                        captured=[],
                        is_capture=False,
                    )
                )
        return moves

    for dr, dc in ALL_DIAGONALS:
        step = 1
        while True:
            if not config.king_flying_moves and step > 1:
                break
            nr, nc = r + step * dr, c + step * dc
            if not is_in_bounds(nr, nc, size) or board[nr][nc] is not None:
                break
            moves.append(
                LegalMove(
                    from_pos=pos,
                    landings=[(nr, nc)],
                    captured=[],
                    is_capture=False,
                )
            )
            step += 1

    return moves


def _captured_king_count(board: list[list[Piece | None]], captured: list[Coord]) -> int:
    count = 0
    for r, c in captured:
        piece = board[r][c]
        if piece is not None and piece.rank == "king":
            count += 1
    return count


def get_legal_moves(
    board: list[list[Piece | None]],
    color: Color,
    config: RulesConfig = DEFAULT_RULES_CONFIG,
) -> list[LegalMove]:
    """Generate all legal complete turns for `color` under `config`."""
    size = config.board_size
    capture_moves: list[LegalMove] = []
    quiet_moves: list[LegalMove] = []

    for r in range(size):
        for c in range(size):
            piece = board[r][c]
            if piece is None or piece.color != color:
                continue
            pos: Coord = (r, c)
            if piece.rank == "man":
                raw_captures = _generate_man_captures(
                    board=board,
                    moving_color=color,
                    start_pos=pos,
                    cur_pos=pos,
                    landings_so_far=[],
                    captured_so_far=[],
                    captured_set=frozenset(),
                    config=config,
                )
            else:
                raw_captures = _generate_king_captures(
                    board=board,
                    moving_color=color,
                    start_pos=pos,
                    cur_pos=pos,
                    landings_so_far=[],
                    captured_so_far=[],
                    captured_set=frozenset(),
                    config=config,
                )

            for seq_landings, seq_captured in raw_captures:
                capture_moves.append(
                    LegalMove(
                        from_pos=pos,
                        landings=seq_landings,
                        captured=seq_captured,
                        is_capture=True,
                    )
                )

    if capture_moves:
        filtered = capture_moves
        if config.maximum_capture:
            max_len = max(len(m.captured) for m in filtered)
            filtered = [m for m in filtered if len(m.captured) == max_len]

        if config.equal_capture_tiebreak == "prefer_kings":
            max_kings = max(_captured_king_count(board, m.captured) for m in filtered)
            filtered = [
                m for m in filtered if _captured_king_count(board, m.captured) == max_kings
            ]

        if config.mandatory_capture:
            return filtered

        for r in range(size):
            for c in range(size):
                piece = board[r][c]
                if piece is not None and piece.color == color:
                    quiet_moves.extend(_generate_quiet_moves_for_piece(board, (r, c), piece, config))
        return [*filtered, *quiet_moves]

    for r in range(size):
        for c in range(size):
            piece = board[r][c]
            if piece is not None and piece.color == color:
                quiet_moves.extend(_generate_quiet_moves_for_piece(board, (r, c), piece, config))

    return quiet_moves

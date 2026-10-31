from typing import Literal

from pydantic import BaseModel, ConfigDict

EqualCaptureTieBreak = Literal["none", "prefer_kings"]
KingCaptureLanding = Literal["any_beyond", "adjacent_only"]


class RulesConfig(BaseModel):
    """Centralized rule configuration for Moroccan Dama (الضامة)."""

    model_config = ConfigDict(frozen=True)

    board_size: int = 8
    mandatory_capture: bool = True
    maximum_capture: bool = True
    equal_capture_tiebreak: EqualCaptureTieBreak = "none"
    king_flying_moves: bool = True
    king_capture_landing: KingCaptureLanding = "any_beyond"
    promote_mid_capture_stops_turn: bool = True
    captured_pieces_block_during_sequence: bool = True
    huffing_enabled: bool = False


DEFAULT_RULES_CONFIG = RulesConfig()

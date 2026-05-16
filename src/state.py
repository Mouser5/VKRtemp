from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Set
from cards import EquipmentType

_card_id_counter = 0


def generate_card_id() -> int:
    global _card_id_counter
    _card_id_counter += 1
    return _card_id_counter


def reset_card_id_counter():
    global _card_id_counter
    _card_id_counter = 0


class PlacedCard(BaseModel):
    unique_id: int = Field(default_factory=generate_card_id)
    template_id: str
    owner_id: Optional[int] = None
    is_rotated_180: bool = False
    is_locked: bool = False
    is_revealed: bool = False


class PlayerState(BaseModel):
    player_id: int
    hand: List[int] = Field(default_factory=list)
    broken_equipments: Set[EquipmentType] = Field(default_factory=set)
    known_secrets: Set[str] = Field(default_factory=set)
    ladders: Set[str] = Field(default_factory=set)
    card_id_to_template: Dict[int, str] = Field(default_factory=dict)
    mulligan_used: bool = False


class MatchState(BaseModel):
    board: Dict[str, PlacedCard] = Field(default_factory=dict)
    players: Dict[int, PlayerState] = Field(default_factory=dict)
    current_player_id: int = 0
    deck: List[int] = Field(default_factory=list)
    deck_template_ids: List[str] = Field(default_factory=list)
    gold_deck: List[str] = Field(default_factory=list)
    is_game_over: bool = False
    turn_number: int = 1
    round_number: int = 1
    first_player_in_round: int = 0
    total_scores: Dict[int, int] = Field(default_factory=lambda: {0: 0, 1: 0})
    round_scores: Dict[int, int] = Field(default_factory=lambda: {0: 0, 1: 0})
    metadata: Any = None
    move_log_dsl: List[str] = Field(default_factory=list)


class ObservablePlayerState(BaseModel):
    player_id: int
    hand: Optional[List[int]] = None
    hand_size: int
    broken_equipments: Set[EquipmentType]


class ObservableMatchState(BaseModel):
    board: Dict[str, PlacedCard]
    players: Dict[int, ObservablePlayerState]
    current_player_id: int
    deck_size: int
    gold_deck_size: int
    is_game_over: bool
    turn_number: int
    round_number: int
    total_scores: Dict[int, int]

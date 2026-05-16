from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class DeckConfig:
    tunnel_cross: int = 10
    tunnel_t: int = 10
    tunnel_straight: int = 8
    tunnel_corner: int = 10
    tunnel_deadend: int = 4
    tunnel_bridge: int = 4
    tunnel_double_corner: int = 4
    tunnel_split_t_up: int = 4
    tunnel_split_t_l: int = 4
    door_blue: int = 3
    door_green: int = 3
    ladder: int = 4
    act_boom: int = 3
    act_key: int = 3
    act_map: int = 4
    brk_LAMP: int = 3
    brk_CART: int = 3
    brk_PICKAXE: int = 3
    rep_LAMP: int = 3
    rep_CART: int = 3
    rep_PICKAXE: int = 3


@dataclass
class GoldConfig:
    gold_positions: List[Tuple[int, int]] = field(
        default_factory=lambda: [
            (-2, -5),
            (0, -5),
            (2, -5),
            (-1, -7),
            (1, -7),
            (0, -9),
        ]
    )
    gold_templates: List[str] = field(
        default_factory=lambda: [
            "gold_1_ud",
            "gold_1_lr",
            "gold_2_corner",
            "gold_2_t",
            "gold_3_cross",
            "gold_3_t",
        ]
    )


@dataclass
class RulesConfig:
    rounds: int = 3
    hand_size_first: int = 4
    hand_size_second: int = 5
    cards_drawn_per_turn: int = 1

    guarantee_card_types: bool = False
    second_extra_draw_t1: bool = False
    first_turn_pass_restriction: bool = False
    mulligan_enabled: bool = False
    second_player_bonus_gold: int = 0
    hand_limit: int = 0


@dataclass
class BoardConfig:
    start_positions: Dict[int, Tuple[int, int]] = field(
        default_factory=lambda: {
            0: (-1, 0),
            1: (1, 0),
        }
    )


@dataclass
class GameConfig:
    deck: DeckConfig = field(default_factory=DeckConfig)
    gold: GoldConfig = field(default_factory=GoldConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)
    board: BoardConfig = field(default_factory=BoardConfig)


@dataclass
class SimConfig:
    agent0_cls_name: str = "heuristic"
    agent1_cls_name: str = "random"
    n_games: int = 1000
    n_workers: int = 4
    verbose: bool = False

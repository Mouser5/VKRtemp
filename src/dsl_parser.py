from typing import Tuple, List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from cards import EquipmentType
from actions import (
    AgentAction,
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
)


class DSLOperation(Enum):
    PASS = 0
    BUILD = 1
    REPAIR = 2
    DISCARD = 3


@dataclass
class DSLPlayerAction:
    operation: DSLOperation
    card_id: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None
    is_rotated: Optional[int] = None
    equipment_id: Optional[int] = None
    second_card_id: Optional[int] = None


class DSLEncoder:
    def __init__(self, game_state: Dict[str, Any], current_player_id: int):
        self.game_state = game_state
        self.current_player_id = current_player_id

    def encode_state(self) -> str:
        lines = []

        board = self.game_state.get("board", {})

        def parse_coord_key(c):
            parts = c.split(";")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
            parts2 = c.split(",")
            if len(parts2) == 2:
                return int(parts2[0]), int(parts2[1])
            return 0, 0

        sorted_coords = sorted(board.keys(), key=parse_coord_key)
        for coord_key in sorted_coords:
            placed = board[coord_key]
            x, y = self._parse_coord(coord_key)
            card_id = placed.get("unique_id", 0)
            is_rot = 1 if placed.get("is_rotated_180", False) else 0
            lines.append(f"{x};{y} {card_id} {is_rot}")

        for pid in [0, 1]:
            broken = (
                self.game_state.get("players", {})
                .get(pid, {})
                .get("broken_equipments", [])
            )
            if broken:
                broken_str = ";".join(str(e) for e in broken)
                lines.append(f"p{pid} {broken_str}")
            else:
                lines.append(f"p{pid} 0")

        player_hand = self.game_state.get("players", {}).get(self.current_player_id, {})
        hand = player_hand.get("hand", [])
        hand_size = len(hand)
        lines.append(str(hand_size))

        if hand:
            hand_str = ";".join(str(card_id) for card_id in hand)
            lines.append(hand_str)

        return "\n".join(lines)

    def _parse_coord(self, coord_str: str) -> Tuple[int, int]:
        if ";" in coord_str:
            parts = coord_str.split(";")
        else:
            parts = coord_str.split(",")
        return int(parts[0]), int(parts[1])


class DSLDecoder:
    def __init__(self, dsl_string: str, game_state: Dict[str, Any], player_id: int):
        self.dsl_string = dsl_string.strip()
        self.game_state = game_state
        self.player_id = player_id
        self._build_card_mapping()

    def _build_card_mapping(self):
        self.card_id_to_template = self.game_state.get("card_id_to_template", {})
        if not self.card_id_to_template:
            hand = (
                self.game_state.get("players", {})
                .get(self.player_id, {})
                .get("hand", [])
            )
            for card_id in hand:
                self.card_id_to_template[card_id] = card_id

    def parse_action(self) -> AgentAction:
        lines = [line.strip() for line in self.dsl_string.split("\n") if line.strip()]
        if not lines:
            raise ValueError("Пустой запрос")

        operation = int(lines[0])

        if operation == DSLOperation.PASS.value:
            return self._parse_pass(lines)
        elif operation == DSLOperation.BUILD.value:
            return self._parse_build(lines)
        elif operation == DSLOperation.REPAIR.value:
            return self._parse_repair(lines)
        elif operation == DSLOperation.DISCARD.value:
            return self._parse_discard(lines)
        else:
            raise ValueError(f"Неизвестная операция: {operation}")

    def _parse_pass(self, lines: List[str]) -> AgentAction:
        hand = (
            self.game_state.get("players", {}).get(self.player_id, {}).get("hand", [])
        )
        if hand:
            raise ValueError("Нельзя пасовать, когда есть карты на руке")
        return ActionDiscard(templates=["pass"])

    def _parse_build(self, lines: List[str]) -> AgentAction:
        if len(lines) < 4:
            raise ValueError("Неверный формат BUILD: нужно 4 строки")

        card_id = int(lines[1])
        coord = lines[2].split(";")
        if len(coord) != 2:
            raise ValueError("Неверный формат координат")
        x, y = int(coord[0]), int(coord[1])
        is_rotated = int(lines[3])

        hand = (
            self.game_state.get("players", {}).get(self.player_id, {}).get("hand", [])
        )
        if card_id not in hand:
            raise ValueError(f"Карта с ID {card_id} не найдена в руке")

        template_id = self.card_id_to_template.get(card_id, card_id)
        return ActionBuild(
            template_id=template_id,
            x=x,
            y=y,
            is_rotated_180=bool(is_rotated),
        )

    def _parse_repair(self, lines: List[str]) -> AgentAction:
        if len(lines) < 3:
            raise ValueError("Неверный формат REPAIR")

        equipment_id = int(lines[1])
        equipment = self._id_to_equipment(equipment_id)

        cards_line = lines[2].split(";")
        if len(cards_line) == 1:
            card_id = int(cards_line[0])
            hand = (
                self.game_state.get("players", {})
                .get(self.player_id, {})
                .get("hand", [])
            )
            if card_id not in hand:
                raise ValueError(f"Карта с ID {card_id} не найдена в руке")
            template_id = self.card_id_to_template.get(card_id, card_id)
            return ActionPlayPlayerUtility(
                template_id=template_id,
                target_player_id=self.player_id,
            )
        elif len(cards_line) == 2:
            card_id1 = int(cards_line[0])
            card_id2 = int(cards_line[1])
            hand = (
                self.game_state.get("players", {})
                .get(self.player_id, {})
                .get("hand", [])
            )
            if card_id1 not in hand or card_id2 not in hand:
                raise ValueError("Карты для экстренной починки не найдены в руке")
            template1 = self.card_id_to_template.get(card_id1, card_id1)
            template2 = self.card_id_to_template.get(card_id2, card_id2)
            return ActionDiscard(
                templates=[template1, template2],
                repair_equipment=equipment,
            )
        else:
            raise ValueError("Неверное количество карт для починки")

    def _parse_discard(self, lines: List[str]) -> AgentAction:
        if len(lines) < 2:
            raise ValueError("Неверный формат DISCARD")

        cards_line = lines[1].split(";")
        templates = []
        for card_id_str in cards_line:
            card_id = int(card_id_str)
            hand = (
                self.game_state.get("players", {})
                .get(self.player_id, {})
                .get("hand", [])
            )
            if card_id not in hand:
                raise ValueError(f"Карта с ID {card_id} не найдена в руке")
            template_id = self.card_id_to_template.get(card_id, card_id)
            templates.append(template_id)

        if len(templates) > 2:
            raise ValueError("Можно сбросить максимум 2 карты")

        return ActionDiscard(templates=templates)

    def _id_to_equipment(self, equipment_id: int) -> EquipmentType:
        equipment_map = {
            1: EquipmentType.LAMP,
            2: EquipmentType.CART,
            3: EquipmentType.PICKAXE,
        }
        if equipment_id not in equipment_map:
            raise ValueError(f"Неизвестный ID инструмента: {equipment_id}")
        return equipment_map[equipment_id]


class DSLActionValidator:
    def __init__(self, game_state: Dict[str, Any], player_id: int):
        self.game_state = game_state
        self.player_id = player_id

    def is_action_valid(self, action: AgentAction) -> Tuple[bool, str]:
        legal_actions = self.game_state.get("legal_actions", [])

        action_dict = self._action_to_dict(action)

        for legal in legal_actions:
            if self._actions_match(action_dict, legal):
                return True, "OK"

        return False, "Ход не является легальным"

    def _action_to_dict(self, action: AgentAction) -> Dict[str, Any]:
        result = {"type": action.type}

        if isinstance(action, ActionBuild):
            result["template_id"] = action.template_id
            result["x"] = action.x
            result["y"] = action.y
            result["is_rotated_180"] = action.is_rotated_180
        elif isinstance(action, ActionPlayBoardUtility):
            result["template_id"] = action.template_id
            result["x"] = action.x
            result["y"] = action.y
        elif isinstance(action, ActionPlayPlayerUtility):
            result["template_id"] = action.template_id
            result["target_player_id"] = action.target_player_id
        elif isinstance(action, ActionDiscard):
            result["templates"] = action.templates
            if action.repair_equipment:
                result["repair_equipment"] = action.repair_equipment.value

        return result

    def _actions_match(
        self, player_action: Dict[str, Any], legal_action: Dict[str, Any]
    ) -> bool:
        if player_action["type"] != legal_action["type"]:
            return False

        if player_action["type"] == "build":
            return (
                player_action.get("template_id") == legal_action.get("template_id")
                and player_action.get("x") == legal_action.get("x")
                and player_action.get("y") == legal_action.get("y")
                and player_action.get("is_rotated_180")
                == legal_action.get("is_rotated_180")
            )
        elif player_action["type"] == "play_board_utility":
            return (
                player_action.get("template_id") == legal_action.get("template_id")
                and player_action.get("x") == legal_action.get("x")
                and player_action.get("y") == legal_action.get("y")
            )
        elif player_action["type"] == "play_player_utility":
            return player_action.get("template_id") == legal_action.get(
                "template_id"
            ) and player_action.get("target_player_id") == legal_action.get(
                "target_player_id"
            )
        elif player_action["type"] == "discard":
            player_templates = sorted(player_action.get("templates", []))
            legal_templates = sorted(legal_action.get("templates", []))
            if player_templates != legal_templates:
                return False
            if player_action.get("repair_equipment") != legal_action.get(
                "repair_equipment"
            ):
                return False
            return True

        return False


def encode_game_state_dsl(game: "Game", player_id: int) -> str:  # noqa: F821
    from board import BoardEngine

    board_dict = {}
    for coord_key, placed in game.state.board.items():
        x, y = BoardEngine.str_to_coord(coord_key)
        board_dict[coord_key] = {
            "unique_id": placed.unique_id,
            "template_id": placed.template_id,
            "is_rotated_180": placed.is_rotated_180,
        }

    players_dict = {}
    for pid, pstate in game.state.players.items():
        players_dict[pid] = {
            "hand": pstate.hand,
            "broken_equipments": [e.value for e in pstate.broken_equipments],
        }

    game_state = {
        "board": board_dict,
        "players": players_dict,
    }

    encoder = DSLEncoder(game_state, player_id)
    return encoder.encode_state()


def decode_player_action_dsl(
    dsl_string: str, game_state: Dict[str, Any], player_id: int
) -> AgentAction:
    decoder = DSLDecoder(dsl_string, game_state, player_id)
    return decoder.parse_action()

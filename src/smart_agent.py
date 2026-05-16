import random
import logging
from typing import Optional, List, Dict, Tuple, Set

from game import Game
from actions import (
    AgentAction, ActionBuild, ActionPlayBoardUtility, ActionPlayPlayerUtility, ActionDiscard
)
from cards import (
    ActionType, EquipmentType, ActionCardTemplate, GoldCardTemplate,
    TunnelCardTemplate, DoorCardTemplate, LadderCardTemplate, PathCardTemplate, Direction
)
from registry import REGISTRY
from board import BoardEngine


class SmartAgent:
    def __init__(self, player_id: int, params: dict = None):
        self.player_id = player_id
        self.logger = logging.getLogger(f"{__name__}_{player_id}")

        self.params = params if params is not None else {
            "rockfall_base": 19.24,
            "rockfall_ladder_bonus": 28.63,
            "rockfall_gold_penalty": 59.87,
            "rockfall_own_path_penalty": 60.24,
            "approach_bonus_base": 60.60,
            "retreat_penalty": 50.12,
            "side_step_bonus": 10.65,
            "dead_end_penalty": 54.73,
            "down_opening_bonus": 20.24,
            "ladder_bonus": 21.24,
            "own_door_bonus": 11.63,
            "enemy_door_penalty": 15.57,
            "max_kept_repairs": 3,
            "max_kept_sabotages": 1,
            "discard_dead_end_value": -22.36,
            "discard_enemy_door_value": -7.86,
            "discard_own_door_value": 11.85,
            "discard_2_exit_value": 12.52,
            "discard_3_4_exit_value": 19.61,
            "discard_ladder_value": 75.00,
            "discard_duplicate_penalty": -12.61,
            "discard_key_useless_value": -24.64,
        }

    def _count_openings(self, tpl) -> int:
        if hasattr(tpl, "openings"):
            return sum([tpl.openings.up, tpl.openings.down, tpl.openings.left, tpl.openings.right])
        return 0

    def _get_unrevealed_gold(self, game: Game) -> List[Dict[str, object]]:
        player_state = game.state.players[self.player_id]
        gold_targets = []
        for coord_key, placed in game.state.board.items():
            tpl = REGISTRY.get(placed.template_id)
            if isinstance(tpl, GoldCardTemplate) and not placed.is_revealed:
                gx, gy = BoardEngine.str_to_coord(coord_key)
                gold_targets.append({
                    "coord": (gx, gy),
                    "value": tpl.gold_value,
                    "known": coord_key in player_state.known_secrets,
                    "coord_key": coord_key,
                })
        return gold_targets

    def _get_frontier(self, game: Game) -> Set[Tuple[int, int]]:
        player_state = game.state.players[self.player_id]
        return game.board_engine.get_player_frontier(
            game.start_positions[self.player_id], self.player_id, game.state.board, player_state.ladders
        )

    def _opens_gold(self, game: Game, action: ActionBuild, target_coord: Tuple[int, int]) -> bool:
        player_state = game.state.players[self.player_id]
        t_id = player_state.card_id_to_template.get(action.template_id)
        if not t_id: return False
        tpl = REGISTRY.get(t_id)

        gx, gy = target_coord
        dx, dy = gx - action.x, gy - action.y

        if abs(dx) + abs(dy) == 1:
            direction = None
            if dx == 0 and dy == 1:
                direction = Direction.UP
            elif dx == 0 and dy == -1:
                direction = Direction.DOWN
            elif dx == -1 and dy == 0:
                direction = Direction.LEFT
            elif dx == 1 and dy == 0:
                direction = Direction.RIGHT

            if direction and game.board_engine._get_effective_opening(tpl, direction, action.is_rotated_180):
                return True
        return False

    def _is_winning_build(self, game: Game, action: ActionBuild, gold_targets: List[Dict]) -> Optional[Dict]:
        for target in gold_targets:
            if self._opens_gold(game, action, target["coord"]):
                return target
        return None

    def choose_action(self, game: Game) -> Optional[AgentAction]:
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None

        opponent_id = 1 - self.player_id
        player_state = game.state.players[self.player_id]

        def _get_tpl(card_id):
            t_id = player_state.card_id_to_template.get(card_id)
            return REGISTRY.get(t_id) if t_id else None

        build_actions = [a for a in legal_actions if isinstance(a, ActionBuild)]
        discard_actions = [a for a in legal_actions if isinstance(a, ActionDiscard)]
        player_util_actions = [a for a in legal_actions if isinstance(a, ActionPlayPlayerUtility)]
        board_util_actions = [a for a in legal_actions if isinstance(a, ActionPlayBoardUtility)]

        gold_targets = self._get_unrevealed_gold(game)

        if player_state.broken_equipments:
            repair_actions = [
                a for a in player_util_actions
                if a.target_player_id == self.player_id
                   and getattr(_get_tpl(a.template_id), "action_type", None) == ActionType.REPAIR
            ]
            if repair_actions:
                return random.choice(repair_actions)

            sabotage_actions = [
                a for a in player_util_actions
                if a.target_player_id == opponent_id
                   and getattr(_get_tpl(a.template_id), "action_type", None) == ActionType.SABOTAGE
            ]
            if sabotage_actions:
                return self._pick_best_sabotage(sabotage_actions, game)

            emergency_discards = [a for a in discard_actions if a.repair_equipment is not None]
            if emergency_discards:
                return self._choose_best_discard(game, emergency_discards)

            if discard_actions:
                return self._choose_best_discard(game, discard_actions)

        winning_builds = []
        for action in build_actions:
            target = self._is_winning_build(game, action, gold_targets)
            if target:
                winning_builds.append((action, target))

        if winning_builds:
            opp_start = game.start_positions[opponent_id]
            # Выбираем золото, ближайшее к точке старта противника
            best_win = min(
                winning_builds,
                key=lambda x: abs(x[1]["coord"][0] - opp_start[0]) + abs(x[1]["coord"][1] - opp_start[1])
            )
            return best_win[0]

        map_actions = [
            a for a in board_util_actions
            if getattr(_get_tpl(a.template_id), "action_type", None) == ActionType.MAP
        ]
        if map_actions:
            best_map = self._choose_best_map_action(game, map_actions)
            if best_map: return best_map

        key_actions = [
            a for a in board_util_actions
            if getattr(_get_tpl(a.template_id), "action_type", None) == ActionType.KEY
        ]
        if key_actions:
            for coord_key, placed in game.state.board.items():
                tpl = REGISTRY.get(placed.template_id)
                if isinstance(tpl, DoorCardTemplate) and placed.is_locked and tpl.door_owner_id != self.player_id:
                    return random.choice(key_actions)  # Открываем дверь

        sabotage_actions = [
            a for a in player_util_actions
            if a.target_player_id == opponent_id
               and getattr(_get_tpl(a.template_id), "action_type", None) == ActionType.SABOTAGE
        ]
        if sabotage_actions:
            return self._pick_best_sabotage(sabotage_actions, game)

        rockfall_actions = [
            a for a in board_util_actions
            if getattr(_get_tpl(a.template_id), "action_type", None) == ActionType.ROCKFALL
        ]
        if rockfall_actions:
            best_rockfall = self._choose_best_rockfall(game, rockfall_actions, opponent_id)
            if best_rockfall: return best_rockfall

        if build_actions:
            best_build = self._choose_best_build_action(game, build_actions, gold_targets)
            if best_build: return best_build

        if discard_actions:
            return self._choose_best_discard(game, discard_actions)

        return random.choice(legal_actions)

    def _choose_best_build_action(self, game: Game, build_actions: List[ActionBuild], gold_targets: List[Dict]) -> \
    Optional[ActionBuild]:
        best_action = None
        best_score = float("-inf")

        base_frontier = self._get_frontier(game)
        if not base_frontier or not gold_targets:
            return None

        closest_gold = None
        min_dist_to_gold = float('inf')

        for target in gold_targets:
            gx, gy = target["coord"]
            dist = min(abs(gx - fx) + abs(gy - fy) for fx, fy in base_frontier)

            if target["known"] and target["value"] == 1 and len(gold_targets) > 1:
                continue

            center_penalty = abs(gx) * 0.1
            effective_dist = dist + center_penalty

            if effective_dist < min_dist_to_gold:
                min_dist_to_gold = effective_dist
                closest_gold = target

        if not closest_gold:
            closest_gold = gold_targets[0]

        gx, gy = closest_gold["coord"]
        player_state = game.state.players[self.player_id]

        for action in build_actions:
            is_blocking = False
            for target in gold_targets:
                tgx, tgy = target["coord"]
                if abs(tgx - action.x) + abs(tgy - action.y) == 1:
                    if not self._opens_gold(game, action, (tgx, tgy)):
                        is_blocking = True
                        break
            if is_blocking:
                continue

            t_id = player_state.card_id_to_template.get(action.template_id)
            if not t_id: continue
            tpl = REGISTRY.get(t_id)
            score = 0.0

            dist_from_new_card = abs(gx - action.x) + abs(gy - action.y)

            if dist_from_new_card < min_dist_to_gold:
                score += self.params["approach_bonus_base"] + (20 - dist_from_new_card) * 2
            elif dist_from_new_card > min_dist_to_gold:
                score -= self.params["retreat_penalty"]
            else:
                score += self.params["side_step_bonus"]

            # Оценка геометрии туннеля
            if self._count_openings(tpl) == 1:
                score -= self.params["dead_end_penalty"]

            has_down = tpl.openings.up if action.is_rotated_180 else tpl.openings.down
            if has_down:
                score += self.params["down_opening_bonus"]

            # Спец-карты
            if isinstance(tpl, LadderCardTemplate):
                score += self.params["ladder_bonus"]
            if isinstance(tpl, DoorCardTemplate):
                if tpl.door_owner_id == self.player_id:
                    score += self.params["own_door_bonus"]
                else:
                    score -= self.params["enemy_door_penalty"]

            if score > best_score:
                best_score = score
                best_action = action

        return best_action

    def _choose_best_map_action(self, game: Game, map_actions: List[ActionPlayBoardUtility]) -> \
            Optional[ActionPlayBoardUtility]:
        best_action = None
        best_val = -1
        known = game.state.players[self.player_id].known_secrets

        for action in map_actions:
            coord_key = BoardEngine.coord_to_str(action.x, action.y)
            if coord_key in known: continue

            placed = game.state.board.get(coord_key)
            if placed:
                tpl = REGISTRY.get(placed.template_id)
                if isinstance(tpl, GoldCardTemplate) and tpl.gold_value > best_val:
                    best_val = tpl.gold_value
                    best_action = action

        return best_action

    def _pick_best_sabotage(self, sabotage_actions: List[ActionPlayPlayerUtility],
                            game: Game) -> ActionPlayPlayerUtility:
        return random.choice(sabotage_actions)

    def _choose_best_rockfall(self, game: Game, rockfall_actions: List[ActionPlayBoardUtility], opponent_id: int) -> \
    Optional[ActionPlayBoardUtility]:
        best_action = None
        best_score = float("-inf")
        opp_start = game.start_positions[opponent_id]
        opponent_state = game.state.players[opponent_id]
        my_reachable = game.board_engine.bfs_reachable_states({game.start_positions[self.player_id]}, self.player_id,
                                                              game.state.board)
        my_reachable_coords = {(x, y) for x, y, _ in my_reachable} if isinstance(my_reachable, set) else set()

        for action in rockfall_actions:
            coord_key = BoardEngine.coord_to_str(action.x, action.y)
            if coord_key not in game.state.board: continue

            score = 0.0
            dist_to_opp = abs(action.x - opp_start[0]) + abs(action.y - opp_start[1])

            score += max(0.0, self.params["rockfall_base"] - dist_to_opp)

            if coord_key in opponent_state.ladders:
                score += self.params["rockfall_ladder_bonus"]

            # Штраф за обвал своего пути
            if (action.x, action.y) in my_reachable_coords:
                score -= self.params["rockfall_own_path_penalty"]

            # Штраф за обвал рядом с золотом
            for g_key, g_placed in game.state.board.items():
                tpl = REGISTRY.get(g_placed.template_id)
                if isinstance(tpl, GoldCardTemplate) and not g_placed.is_revealed:
                    gx, gy = BoardEngine.str_to_coord(g_key)
                    if abs(action.x - gx) + abs(action.y - gy) <= 2:
                        score -= self.params["rockfall_gold_penalty"]

            if score > best_score:
                best_score = score
                best_action = action

        return best_action

    def _get_card_discard_value(self, game: Game, template_id: str, repair_counts: dict,
                                sabotage_counts: dict) -> float:
        if not template_id: return 0.0
        tpl = REGISTRY.get(template_id)

        # Оценка действий
        if isinstance(tpl, ActionCardTemplate):
            if tpl.action_type == ActionType.REPAIR:
                return 0.0 if repair_counts[tpl.equipment_type] <= self.params["max_kept_repairs"] else self.params[
                    "discard_duplicate_penalty"]
            elif tpl.action_type == ActionType.SABOTAGE:
                return 0.0 if sabotage_counts[tpl.equipment_type] <= self.params["max_kept_sabotages"] else self.params[
                    "discard_duplicate_penalty"]
            elif tpl.action_type == ActionType.KEY:
                # Если у противника нет закрытых дверей на поле, ключ бесполезен
                has_enemy_doors = any(
                    isinstance(REGISTRY.get(p.template_id), DoorCardTemplate) and p.is_locked and REGISTRY.get(
                        p.template_id).door_owner_id != self.player_id
                    for p in game.state.board.values()
                )
                return 0.0 if has_enemy_doors else self.params["discard_key_useless_value"]
            return 0.0

        # Оценка туннелей по геометрии
        if isinstance(tpl, (TunnelCardTemplate, PathCardTemplate)):
            if isinstance(tpl, DoorCardTemplate):
                return self.params["discard_own_door_value"] if tpl.door_owner_id == self.player_id else self.params[
                    "discard_enemy_door_value"]
            if isinstance(tpl, LadderCardTemplate):
                return self.params["discard_ladder_value"]

            openings = self._count_openings(tpl)
            if openings == 1:
                return self.params["discard_dead_end_value"]
            elif openings == 2:
                return self.params["discard_2_exit_value"]
            else:
                return self.params["discard_3_4_exit_value"]

        return 0.0

    def _choose_best_discard(self, game: Game, discard_actions: List[ActionDiscard]) -> AgentAction:
        player_state = game.state.players[self.player_id]

        repair_counts = {eq: 0 for eq in EquipmentType}
        sabotage_counts = {eq: 0 for eq in EquipmentType}
        for c_id in player_state.hand:
            t_id = player_state.card_id_to_template.get(c_id)
            if t_id:
                tpl = REGISTRY.get(t_id)
                if isinstance(tpl, ActionCardTemplate):
                    if tpl.action_type == ActionType.REPAIR: repair_counts[tpl.equipment_type] += 1
                    if tpl.action_type == ActionType.SABOTAGE: sabotage_counts[tpl.equipment_type] += 1

        best_action = None
        min_kept_value = float("inf")

        for action in discard_actions:
            combined_value = 0.0
            for t_id in action.templates:
                template_str = player_state.card_id_to_template.get(t_id)
                combined_value += self._get_card_discard_value(game, template_str, repair_counts, sabotage_counts)

            if not action.repair_equipment and len(action.templates) == 2:
                if combined_value >= 0:
                    continue

            if combined_value < min_kept_value:
                min_kept_value = combined_value
                best_action = action

        return best_action if best_action else random.choice(discard_actions)
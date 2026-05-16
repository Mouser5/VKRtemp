"""
Робот HeuristicRobot для игры "Гномы-вредители: Дуэль"

Продвинутый робот с комплексными эвристиками:
1. Чинит инструменты, если сломаны
2. Использует карты сокровищ (MAP) для обнаружения золота
3. Открывает двери ключами
4. Строит пути к нераскрытому золоту
5. Ломает инструменты противника
6. Использует обвалы для блокировки противника
7. Случайный ход если ничего не подходит
"""

import random
from typing import Optional, List

from actions import (
    AgentAction,
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
)
from cards import (
    ActionType,
    GoldCardTemplate,
    DoorCardTemplate,
    LadderCardTemplate,
)
from registry import REGISTRY
from board import BoardEngine


class HeuristicRobot:
    """Продвинутый робот с эвристиками."""

    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game) -> Optional[AgentAction]:
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None
        return self._select_best_action(game, legal_actions)

    def _get_template_id(self, game, action) -> Optional[str]:
        """Получить template_id из action (может быть card_id или template_id)."""
        tid = action.template_id
        if isinstance(tid, str):
            return tid
        return game.state.players[self.player_id].card_id_to_template.get(tid)

    def _select_best_action(
        self, game, legal_actions: List[AgentAction]
    ) -> AgentAction:
        opponent_id = 1 - self.player_id
        player_state = game.state.players[self.player_id]
        game.state.players[opponent_id]

        # === ПРИОРИТЕТ 1: Чиним инструменты ===
        if player_state.broken_equipments:
            for action in legal_actions:
                if isinstance(action, ActionPlayPlayerUtility):
                    tpl_id = self._get_template_id(game, action)
                    if not tpl_id or tpl_id not in REGISTRY.templates:
                        continue
                    tpl = REGISTRY.get(tpl_id)
                    if (
                        hasattr(tpl, "action_type")
                        and tpl.action_type == ActionType.REPAIR
                        and action.target_player_id == self.player_id
                    ):
                        return action

        # === ПРИОРИТЕТ 2: MAP карты ===
        for action in legal_actions:
            if isinstance(action, ActionPlayBoardUtility):
                tpl_id = self._get_template_id(game, action)
                if not tpl_id or tpl_id not in REGISTRY.templates:
                    continue
                tpl = REGISTRY.get(tpl_id)
                if hasattr(tpl, "action_type") and tpl.action_type == ActionType.MAP:
                    return action

        # === ПРИОРИТЕТ 3: Ключи для своих дверей ===
        for action in legal_actions:
            if isinstance(action, ActionPlayBoardUtility):
                tpl_id = self._get_template_id(game, action)
                if not tpl_id or tpl_id not in REGISTRY.templates:
                    continue
                tpl = REGISTRY.get(tpl_id)
                if hasattr(tpl, "action_type") and tpl.action_type == ActionType.KEY:
                    return action

        # === ПРИОРИТЕТ 4: Строим туннели ===
        build_actions = [a for a in legal_actions if isinstance(a, ActionBuild)]
        if build_actions:
            return self._choose_best_build(build_actions, game)

        # === ПРИОРИТЕТ 5: Ломаем инструменты ===
        for action in legal_actions:
            if isinstance(action, ActionPlayPlayerUtility):
                tpl_id = self._get_template_id(game, action)
                if not tpl_id or tpl_id not in REGISTRY.templates:
                    continue
                tpl = REGISTRY.get(tpl_id)
                if (
                    hasattr(tpl, "action_type")
                    and tpl.action_type == ActionType.SABOTAGE
                    and action.target_player_id == opponent_id
                ):
                    return action

        # === ПРИОРИТЕТ 6: Обвалы ===
        for action in legal_actions:
            if isinstance(action, ActionPlayBoardUtility):
                tpl_id = self._get_template_id(game, action)
                if not tpl_id or tpl_id not in REGISTRY.templates:
                    continue
                tpl = REGISTRY.get(tpl_id)
                if (
                    hasattr(tpl, "action_type")
                    and tpl.action_type == ActionType.ROCKFALL
                ):
                    return action

        # Случайный ход
        return random.choice(legal_actions)

    def _choose_best_build(self, build_actions, game) -> AgentAction:
        """Выбрать лучшую позицию для постройки - ближе к золоту."""
        best_action = None
        best_score = float("-inf")

        for action in build_actions:
            score = 0
            tpl_id = self._get_template_id(game, action)
            if not tpl_id or tpl_id not in REGISTRY.templates:
                continue
            tpl = REGISTRY.get(tpl_id)

            # Ближе к нераскрытому золоту - лучше
            min_dist = self._distance_to_gold(action.x, action.y, game)
            if min_dist is not None:
                score += max(0, 20 - min_dist) * 3

            # Лестницы полезны
            if isinstance(tpl, LadderCardTemplate):
                score += 10

            # Двери - хуже
            if isinstance(tpl, DoorCardTemplate):
                score -= 5

            if score > best_score:
                best_score = score
                best_action = action

        return best_action or build_actions[0]

    def _distance_to_gold(self, x: int, y: int, game) -> Optional[int]:
        """Расстояние до ближайшего нераскрытого золота."""
        min_dist = None
        for coord_key, placed in game.state.board.items():
            if not isinstance(placed.template_id, str):
                continue
            if placed.template_id not in REGISTRY.templates:
                continue
            tpl = REGISTRY.get(placed.template_id)
            if isinstance(tpl, GoldCardTemplate) and not placed.is_revealed:
                gx, gy = BoardEngine.str_to_coord(coord_key)
                dist = abs(gx - x) + abs(gy - y)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
        return min_dist


Robot = HeuristicRobot

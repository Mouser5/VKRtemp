"""
Робот SmarterRobot для игры "Гномы-вредители: Дуэль"

Более умный робот с простыми эвристиками:
1. Чинит инструменты, если сломаны
2. Строит туннели
3. Ломает инструменты противника
4. Случайный ход если ничего не подходит
"""

import random

from actions import ActionBuild, ActionPlayPlayerUtility


class SmarterRobot:
    """Умный робот с базовыми эвристиками."""

    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None

        player_state = game.state.players[self.player_id]
        opponent_id = 1 - self.player_id

        # Получаем маппинг card_id -> template_id для текущего игрока
        card_id_to_template = player_state.card_id_to_template

        def get_template_id(action):
            """Получить template_id из action (может быть card_id или template_id)."""
            tid = action.template_id
            if isinstance(tid, str):
                return tid
            return card_id_to_template.get(tid, tid)

        # Приоритет 1: Чиним свои инструменты если сломаны
        if player_state.broken_equipments:
            from cards import ActionType

            for action in legal_actions:
                if isinstance(action, ActionPlayPlayerUtility):
                    from registry import REGISTRY

                    tpl_id = get_template_id(action)
                    if tpl_id and tpl_id in REGISTRY.templates:
                        tpl = REGISTRY.get(tpl_id)
                        if (
                            hasattr(tpl, "action_type")
                            and tpl.action_type == ActionType.REPAIR
                            and action.target_player_id == self.player_id
                        ):
                            return action

        # Приоритет 2: Строим туннели
        for action in legal_actions:
            if isinstance(action, ActionBuild):
                return action

        # Приоритет 3: Ломаем инструменты противника
        opponent_state = game.state.players[opponent_id]
        if not opponent_state.broken_equipments:
            from cards import ActionType

            for action in legal_actions:
                if isinstance(action, ActionPlayPlayerUtility):
                    from registry import REGISTRY

                    tpl_id = get_template_id(action)
                    if tpl_id and tpl_id in REGISTRY.templates:
                        tpl = REGISTRY.get(tpl_id)
                        if (
                            hasattr(tpl, "action_type")
                            and tpl.action_type == ActionType.SABOTAGE
                            and action.target_player_id == opponent_id
                        ):
                            return action

        # Иначе - случайный ход
        return random.choice(legal_actions)


Robot = SmarterRobot

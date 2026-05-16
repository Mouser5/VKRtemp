"""
Пример простого робота для игры "Гномы-вредители: Дуэль"

Этот робот выбирает случайный ход из списка легальных действий.
Используйте его как шаблон для создания своего робота.
"""

import random

# Примечание: эти импорты работают внутри веб-интерфейса
# При локальном тестировании используйте: from actions import AgentAction


class MyFirstRobot:
    """
    Простейший робот, который выбирает случайный легальный ход.
    """

    def __init__(self, player_id: int):
        """
        Конструктор робота.

        Args:
            player_id: ID игрока (0 или 1)
        """
        self.player_id = player_id

    def choose_action(self, game):
        """
        Выбирает действие для выполнения.

        Args:
            game: Объект игры с текущим состоянием

        Returns:
            AgentAction или None, если нет легальных ходов
        """
        # Получаем список всех легальных ходов
        legal_actions = game.get_legal_actions()

        # Если ходов нет, возвращаем None
        if not legal_actions:
            return None

        # Выбираем случайный ход
        return random.choice(legal_actions)


class SmarterRobot:
    """
    Более умный робот с простыми эвристиками.
    """

    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None

        # Импортируем типы действий (доступны внутри игры)
        from actions import ActionBuild, ActionPlayPlayerUtility

        # Приоритет 1: Чиним инструменты, если сломаны
        player_state = game.state.players[self.player_id]
        if player_state.broken_equipments:
            for action in legal_actions:
                if isinstance(action, ActionPlayPlayerUtility):
                    # Ищем действие починки для себя
                    from registry import REGISTRY
                    from cards import ActionType

                    tpl = REGISTRY.get(action.template_id)
                    if (
                        hasattr(tpl, "action_type")
                        and tpl.action_type == ActionType.REPAIR
                    ):
                        if action.target_player_id == self.player_id:
                            return action

        # Приоритет 2: Строим, если можем
        for action in legal_actions:
            if isinstance(action, ActionBuild):
                return action

        # Иначе - случайный ход
        return random.choice(legal_actions)


# ВАЖНО: Класс, который будет использоваться, должен быть доступен
# Вы можете переименовать класс или добавить алиас:
Robot = MyFirstRobot

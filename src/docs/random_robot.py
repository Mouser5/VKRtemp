"""
Робот RandomRobot для игры "Гномы-вредители: Дуэль"

Этот робот выбирает случайный ход из списка легальных действий.
Простейшая стратегия для ознакомления с игрой.
"""

import random


class RandomRobot:
    """Простейший робот, который выбирает случайный легальный ход."""

    def __init__(self, player_id: int):
        self.player_id = player_id

    def choose_action(self, game):
        legal_actions = game.get_legal_actions()
        if not legal_actions:
            return None
        return random.choice(legal_actions)


Robot = RandomRobot

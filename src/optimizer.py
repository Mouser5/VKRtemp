import optuna
import logging
from game import Game
from heuristic_agent import HeuristicAgent  # Наш стабильный baseline для спарринга
from smart_agent import SmartAgent  # Наш настраиваемый бот

# Отключаем лишние логи игры, чтобы не засорять консоль (Optuna сама будет выводить прогресс)
logging.getLogger().setLevel(logging.ERROR)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def objective(trial):
    """
    Целевая функция для Optuna.
    Генерирует набор гиперпараметров, проводит N матчей и возвращает Win Rate.
    """
    # Задаем диапазоны поиска для КАЖДОГО гиперпараметра из нашей 7-уровневой архитектуры
    params = {
        # --- Саботаж и Обвалы ---
        "sabotage_lamp_weight": trial.suggest_float("sabotage_lamp_weight", 1.0, 5.0),
        "sabotage_cart_weight": trial.suggest_float("sabotage_cart_weight", 1.0, 5.0),
        "sabotage_pickaxe_weight": trial.suggest_float("sabotage_pickaxe_weight", 0.5, 4.0),
        "rockfall_base": trial.suggest_float("rockfall_base", 5.0, 30.0),
        "rockfall_ladder_bonus": trial.suggest_float("rockfall_ladder_bonus", 10.0, 50.0),
        "rockfall_gold_penalty": trial.suggest_float("rockfall_gold_penalty", 20.0, 80.0),
        "rockfall_own_path_penalty": trial.suggest_float("rockfall_own_path_penalty", 20.0, 80.0),

        # --- Строительство (Target Lock) ---
        "approach_bonus_base": trial.suggest_float("approach_bonus_base", 20.0, 80.0),
        "retreat_penalty": trial.suggest_float("retreat_penalty", 20.0, 80.0),
        "side_step_bonus": trial.suggest_float("side_step_bonus", 0.0, 20.0),
        "dead_end_penalty": trial.suggest_float("dead_end_penalty", 10.0, 70.0),
        "down_opening_bonus": trial.suggest_float("down_opening_bonus", 0.0, 30.0),
        "ladder_bonus": trial.suggest_float("ladder_bonus", 5.0, 40.0),
        "own_door_bonus": trial.suggest_float("own_door_bonus", 0.0, 25.0),
        "enemy_door_penalty": trial.suggest_float("enemy_door_penalty", 5.0, 30.0),

        # --- Управление рукой и Сброс ---
        # Обрати внимание: здесь используем suggest_int, так как количество карт - целое число
        "max_kept_repairs": trial.suggest_int("max_kept_repairs", 0, 3),
        "max_kept_sabotages": trial.suggest_int("max_kept_sabotages", 0, 3),

        "discard_dead_end_value": trial.suggest_float("discard_dead_end_value", -40.0, 0.0),
        "discard_enemy_door_value": trial.suggest_float("discard_enemy_door_value", -30.0, 0.0),
        "discard_own_door_value": trial.suggest_float("discard_own_door_value", 0.0, 20.0),
        "discard_2_exit_value": trial.suggest_float("discard_2_exit_value", 0.0, 20.0),
        "discard_3_4_exit_value": trial.suggest_float("discard_3_4_exit_value", 10.0, 50.0),
        "discard_ladder_value": trial.suggest_float("discard_ladder_value", 20.0, 80.0),
        "discard_duplicate_penalty": trial.suggest_float("discard_duplicate_penalty", -30.0, 0.0),
        "discard_key_useless_value": trial.suggest_float("discard_key_useless_value", -40.0, 0.0)
    }

    # Количество игр в одной итерации. 150 - хороший баланс между скоростью и точностью (Закон больших чисел).
    num_games = 150
    wins = 0

    # Прогоняем турнир: Наш SmartAgent (с мутированными параметрами) против HeuristicAgent
    for _ in range(num_games):
        game = Game()
        agents = {
            0: SmartAgent(0, params=params),
            1: HeuristicAgent(1)
        }

        while not game.is_game_over():
            curr_p = game.state.current_player_id
            action = agents[curr_p].choose_action(game)
            if not action:
                break
            game.step(action)

        scores = game.calculate_scores()
        if scores[0] > scores[1]:
            wins += 1
        elif scores[0] == scores[1]:
            wins += 0.5  # Ничью можно считать как полпобеды для более гладкого графика (по желанию)

    win_rate = wins / num_games
    if win_rate >= 0.60:
        print(f'Попытка {trial.number} Результат:    {win_rate:.4f} ')
        # Если хочешь сразу видеть параметры удачной попытки, раскомментируй строку ниже:
        if win_rate>=0.87:
            print(f"Параметры: {params}\n")
    return win_rate


if __name__ == "__main__":
    print("Начинаем байесовскую оптимизацию гиперпараметров (TPE)...")

    # Создаем объект исследования. Цель - максимизировать Win Rate.
    study = optuna.create_study(direction="maximize")

    # Запускаем 150 итераций.
    # 150 итераций * 150 игр = 22 500 матчей. Это может занять минут 10-15.
    study.optimize(objective, n_trials=150)

    print("\n" + "=" * 40)
    print("ОПТИМИЗАЦИЯ ЗАВЕРШЕНА")
    print("=" * 40)
    print(f"ЛУЧШИЙ ПРОЦЕНТ ПОБЕД: {study.best_value * 100:.1f}%")
    print("\nЛучшие гиперпараметры для копирования в smart_agent.py:")

    print("self.params = {")
    for key, value in study.best_params.items():
        # Форматируем красиво: целые числа без точки, дробные с двумя знаками после запятой
        if isinstance(value, int):
            print(f'    "{key}": {value},')
        else:
            print(f'    "{key}": {value:.2f},')
    print("}")

    print("\nСохранение истории попыток в файл...")
    df = study.trials_dataframe()
    df.to_csv("./results/trials_history.csv", index=False)
    print("Готово! Файл 'trials_history.csv' сохранен в папке с проектом.")
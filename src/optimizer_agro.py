import optuna
import logging
from game import Game
from heuristic_agent import HeuristicAgent  # Наш стабильный baseline для спарринга
from smart_agent import SmartAgent  # Наш настраиваемый бот

logging.getLogger().setLevel(logging.ERROR)
optuna.logging.set_verbosity(optuna.logging.WARNING)

# =====================================================================
# АРХЕТИП 1: РАШЕР (АГРО-БОТ)
# Цель: Максимальная скорость прокладки туннеля к золоту.
# =====================================================================
def objective_rusher(trial):
    params = {
        # --- ЗАФИКСИРОВАННЫЕ ПАРАМЕТРЫ (Принудительно отключаем саботаж) ---
        "sabotage_lamp_weight": 0.0,
        "sabotage_cart_weight": 0.0,
        "sabotage_pickaxe_weight": 0.0,
        "rockfall_base": 0.0,
        "rockfall_ladder_bonus": 0.0,
        "rockfall_gold_penalty": 100.0,
        "rockfall_own_path_penalty": 100.0,
        "max_kept_sabotages": 0,  # Запрещаем копить карты поломки

        # --- ОПТИМИЗИРУЕМЫЕ ПАРАМЕТРЫ (Движение и сброс) ---
        "approach_bonus_base": trial.suggest_float("approach_bonus_base", 30.0, 100.0),
        "retreat_penalty": trial.suggest_float("retreat_penalty", 30.0, 100.0),
        "side_step_bonus": trial.suggest_float("side_step_bonus", 0.0, 20.0),
        "dead_end_penalty": trial.suggest_float("dead_end_penalty", 20.0, 80.0),
        "down_opening_bonus": trial.suggest_float("down_opening_bonus", 10.0, 50.0),
        "ladder_bonus": trial.suggest_float("ladder_bonus", 10.0, 50.0),
        "own_door_bonus": trial.suggest_float("own_door_bonus", 0.0, 20.0),
        "enemy_door_penalty": trial.suggest_float("enemy_door_penalty", 5.0, 40.0),

        "max_kept_repairs": trial.suggest_int("max_kept_repairs", 0, 2),
        "discard_dead_end_value": trial.suggest_float("discard_dead_end_value", -50.0, 0.0),
        "discard_enemy_door_value": trial.suggest_float("discard_enemy_door_value", -50.0, 0.0),
        "discard_own_door_value": trial.suggest_float("discard_own_door_value", -20.0, 20.0),
        "discard_2_exit_value": trial.suggest_float("discard_2_exit_value", -10.0, 30.0),
        "discard_3_4_exit_value": trial.suggest_float("discard_3_4_exit_value", 20.0, 80.0),
        "discard_ladder_value": trial.suggest_float("discard_ladder_value", 30.0, 100.0),
        "discard_duplicate_penalty": trial.suggest_float("discard_duplicate_penalty", -40.0, 0.0),
        "discard_key_useless_value": trial.suggest_float("discard_key_useless_value", -50.0, 0.0)
    }

    num_games = 150
    wins = 0
    total_gold_found = 0
    total_turns = 0

    for _ in range(num_games):
        game = Game()
        agents = {0: SmartAgent(0, params=params), 1: HeuristicAgent(1)}

        while not game.is_game_over():
            curr_p = game.state.current_player_id
            action = agents[curr_p].choose_action(game)
            if not action: break
            game.step(action)

        scores = game.calculate_scores()
        if scores[0] > scores[1]:
            wins += 1
        elif scores[0] == scores[1]:
            wins += 0.5

        total_gold_found += scores[0]  # Записываем добытое золото Игрока 0
        total_turns += game.state.turn_number

    win_rate = wins / num_games
    avg_gold_per_turn = total_gold_found / (total_turns / 2)  # Делим на 2, т.к. turn_number общий

    # ФУНКЦИЯ НАГРАДЫ РАШЕРА: Победы + Скорость добычи
    # Умножаем скорость на 2.0, чтобы вес был сопоставим с Win Rate
    rusher_score = win_rate + (avg_gold_per_turn * 2.0)
    if win_rate >= 0.85:
        print(f'Попытка {trial.number} Результат:    {rusher_score:.3f} = {win_rate:.3f} + {avg_gold_per_turn * 2.0:.3f}')
        # Если хочешь сразу видеть параметры удачной попытки, раскомментируй строку ниже:
        if win_rate>= 0.879:
            print(f"Параметры: {params}\n")


    return rusher_score


if __name__ == "__main__":
    print("\n=== Запуск поиска идеального РАШЕРА ===")
    study_rusher = optuna.create_study(direction="maximize")
    study_rusher.optimize(objective_rusher, n_trials=150)

    print("\nЛУЧШИЕ ПАРАМЕТРЫ РАШЕРА:")
    for k, v in study_rusher.best_params.items():
        print(f'    "{k}": {v if isinstance(v, int) else round(v, 2)},')

    # === ДОБАВЛЕН СПОСОБ 2: Экспорт в CSV ===
    print("\nСохранение истории попыток в файл...")
    df = study_rusher.trials_dataframe()
    # Сохраняем в CSV (разделитель - запятая, без столбца с индексами)
    df.to_csv("./results/rusher_trials_history.csv", index=False)
    print("Готово! Файл 'rusher_trials_history.csv' сохранен в папке с проектом.")

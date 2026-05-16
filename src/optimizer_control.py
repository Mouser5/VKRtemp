import optuna
import logging
from game import Game
from heuristic_agent import HeuristicAgent  # Наш стабильный baseline для спарринга
from smart_agent import SmartAgent  # Наш настраиваемый бот

logging.getLogger().setLevel(logging.ERROR)
optuna.logging.set_verbosity(optuna.logging.WARNING)


# =====================================================================
# АРХЕТИП 2: КОНТРОЛЬ (САБОТЕР)
# Цель: Парализовать противника и не дать ему собирать золото.
# =====================================================================
def objective_control(trial):
    params = {
        # --- ЗАФИКСИРОВАННЫЕ ПАРАМЕТРЫ (Среднее строительство) ---
        "approach_bonus_base": 40.0,
        "retreat_penalty": 50.0,
        "side_step_bonus": 7.0,
        "dead_end_penalty": 40.0,
        "down_opening_bonus": 10.0,
        "own_door_bonus": 10.0,
        "enemy_door_penalty": 15.0,
        # --- ОПТИМИЗИРУЕМЫЕ ПАРАМЕТРЫ (Агрессия и контроль руки) ---
        "sabotage_lamp_weight": trial.suggest_float("sabotage_lamp_weight", 5.0, 30.0),
        "sabotage_cart_weight": trial.suggest_float("sabotage_cart_weight", 5.0, 30.0),
        "sabotage_pickaxe_weight": trial.suggest_float(
            "sabotage_pickaxe_weight", 2.0, 20.0
        ),
        "rockfall_base": trial.suggest_float("rockfall_base", 10.0, 50.0),
        "rockfall_ladder_bonus": trial.suggest_float(
            "rockfall_ladder_bonus", 20.0, 80.0
        ),
        "rockfall_gold_penalty": trial.suggest_float(
            "rockfall_gold_penalty", 10.0, 100.0
        ),
        "rockfall_own_path_penalty": trial.suggest_float(
            "rockfall_own_path_penalty", 10.0, 100.0
        ),
        "max_kept_sabotages": trial.suggest_int(
            "max_kept_sabotages", 1, 4
        ),  # Разрешаем копить поломки!
        "max_kept_repairs": trial.suggest_int("max_kept_repairs", 1, 3),
        "ladder_bonus": trial.suggest_float(
            "ladder_bonus", 5.0, 50.0
        ),  # Лестницы важны для контроля
        "discard_dead_end_value": trial.suggest_float(
            "discard_dead_end_value", -50.0, 0.0
        ),
        "discard_enemy_door_value": trial.suggest_float(
            "discard_enemy_door_value", -50.0, 0.0
        ),
        "discard_own_door_value": trial.suggest_float(
            "discard_own_door_value", -20.0, 20.0
        ),
        "discard_2_exit_value": trial.suggest_float(
            "discard_2_exit_value", -10.0, 30.0
        ),
        "discard_3_4_exit_value": trial.suggest_float(
            "discard_3_4_exit_value", 20.0, 80.0
        ),
        "discard_ladder_value": trial.suggest_float(
            "discard_ladder_value", 30.0, 100.0
        ),
        "discard_duplicate_penalty": trial.suggest_float(
            "discard_duplicate_penalty", -40.0, 0.0
        ),
        "discard_key_useless_value": trial.suggest_float(
            "discard_key_useless_value", -50.0, 0.0
        ),
    }

    num_games = 150
    wins = 0
    total_turns = 0
    total_opp_broken_turns = 0
    total_opp_gold = 0

    for _ in range(num_games):
        game = Game()
        agents = {0: SmartAgent(0, params=params), 1: HeuristicAgent(1)}

        while not game.is_game_over():
            curr_p = game.state.current_player_id

            # Подсчет времени под контролем: считаем ходы, когда противник сломан
            if curr_p == 0 and len(game.state.players[1].broken_equipments) > 0:
                total_opp_broken_turns += 1

            action = agents[curr_p].choose_action(game)
            if not action:
                break
            game.step(action)

        scores = game.calculate_scores()
        if scores[0] > scores[1]:
            wins += 1
        elif scores[0] == scores[1]:
            wins += 0.5

        total_opp_gold += scores[1]
        total_turns += game.state.turn_number

    win_rate = wins / num_games
    broken_time_ratio = total_opp_broken_turns / (
        total_turns / 2
    )  # Процент времени, когда враг сломан
    avg_opp_gold = total_opp_gold / num_games

    # ФУНКЦИЯ НАГРАДЫ КОНТРОЛЯ: Победы + Мучения противника - Добытое противником золото
    control_score = win_rate + (broken_time_ratio * 0.5) - (avg_opp_gold * 0.1)
    if win_rate >= 0.85:
        print(
            f"Попытка {trial.number} Результат:    {control_score:.3f} = {win_rate:.3f} + {broken_time_ratio * 0.5:.3f} - {avg_opp_gold * 0.1}"
        )
        # Если хочешь сразу видеть параметры удачной попытки, раскомментируй строку ниже:
        if win_rate >= 0.90:
            print(f"Параметры: {params}\n")

    return control_score


if __name__ == "__main__":
    study_control = optuna.create_study(direction="maximize")
    study_control.optimize(objective_control, n_trials=150)
    print("\nЛУЧШИЕ ПАРАМЕТРЫ КОНТРОЛЯ:")
    for k, v in study_control.best_params.items():
        print(f'    "{k}": {v if isinstance(v, int) else round(v, 2)},')

    # === ДОБАВЛЕН СПОСОБ 2: Экспорт в CSV ===
    print("\nСохранение истории попыток в файл...")
    df = study_control.trials_dataframe()
    # Сохраняем в CSV (разделитель - запятая, без столбца с индексами)
    df.to_csv("./results/control_trials_history.csv", index=False)
    print("Готово! Файл 'control_trials_history.csv' сохранен в папке с проектом.")

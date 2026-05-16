import optuna
import logging
from game import Game
from smart_agent import SmartAgent
from src.cards import GoldCardTemplate
from src.registry import REGISTRY
from src.view import ConsoleView

logging.getLogger().setLevel(logging.ERROR)
# optuna.logging.set_verbosity(optuna.logging.WARNING)

# 1. Вставляем наши эталонные словари
AGRO_PARAMS = {
    "sabotage_lamp_weight": 0.1, "sabotage_cart_weight": 0.1, "sabotage_pickaxe_weight": 0.1,
    "rockfall_base": 0.1, "rockfall_ladder_bonus": 0.1, "rockfall_gold_penalty": 100.0,
    "rockfall_own_path_penalty": 100.0,
    "approach_bonus_base": 40.75, "retreat_penalty": 48.72, "side_step_bonus": 2.89,
    "dead_end_penalty": 21.97, "down_opening_bonus": 19.07, "ladder_bonus": 26.35,
    "own_door_bonus": 13.48, "enemy_door_penalty": 16.26, "max_kept_repairs": 0, "max_kept_sabotages": 0,
    "discard_dead_end_value": -12.16, "discard_enemy_door_value": -32.67, "discard_own_door_value": -12.55,
    "discard_2_exit_value": -7.28, "discard_3_4_exit_value": 53.57, "discard_ladder_value": 89.77,
    "discard_duplicate_penalty": -12.75, "discard_key_useless_value": -35.19,
}

CONTROL_PARAMS = {
    "approach_bonus_base": 40.0,
    "retreat_penalty": 50.0,
    "side_step_bonus": 7.0,
    "dead_end_penalty": 40.0,
    "down_opening_bonus": 10.0,
    "own_door_bonus": 10.0,
    "enemy_door_penalty": 15.0,
    "sabotage_lamp_weight": 22.62,
    "sabotage_cart_weight": 18.17,
    "sabotage_pickaxe_weight": 18.01,
    "rockfall_base": 42.81,
    "rockfall_ladder_bonus": 28.17,
    "rockfall_gold_penalty": 62.95,
    "rockfall_own_path_penalty": 10.05,
    "max_kept_sabotages": 4,
    "max_kept_repairs": 2,
    "ladder_bonus": 30.62,
    "discard_dead_end_value": -49.16,
    "discard_enemy_door_value": -32.87,
    "discard_own_door_value": 8.37,
    "discard_2_exit_value": -5.99,
    "discard_3_4_exit_value": 44.18,
    "discard_ladder_value": 69.85,
    "discard_duplicate_penalty": -3.46,
    "discard_key_useless_value": -34.71,
}

MIDRANGE_PARAMS = {
    "sabotage_lamp_weight": 1.61,
    "sabotage_cart_weight": 2.10,
    "sabotage_pickaxe_weight": 3.43,
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

def play_matchup(agent0_params, agent1_params, deck_config, num_games=250):
    wins_0, draws, is_win_by_gold = 0, 0, 0
    steps=0
    for i in range(num_games):
        game = Game(config=deck_config)  # Передаем состав колоды!
        agents = {0: SmartAgent(0, params=agent0_params), 1: SmartAgent(1, params=agent1_params)}
        # print(i)
        # if (i == 13):
        #     print(i)
        while not game.is_game_over():
            while not game.is_round_over():
                curr_p = game.state.current_player_id
                action = agents[curr_p].choose_action(game)
                # if not action: break
                steps+=1
                game.step(action)
            game.check_round_end()
            # view = ConsoleView()
            # view.print_board(game.state)
        scores, by_gold = game.calculate_scores()
        if scores[0] > scores[1]:
            wins_0 += 1
        elif scores[0] == scores[1]:
            draws += 1
        is_win_by_gold+=by_gold


    return wins_0 / num_games, draws / num_games, is_win_by_gold /(2*num_games), steps/(2*num_games)


def objective_meta_balance(trial):
    # Optuna подбирает идеальный состав колоды
    # Даем уникальные имена для генерации и используем целочисленное деление (//)
    straight_val = 4
    corn = 2
    split = 1
    door = trial.suggest_int("door_count_base", 1, 2)
    sabot = trial.suggest_int("sabotage_count", 1, 3)

    deck_config = {
        # Главные рычаги
        "tunnel_cross": 1 * 2,
        "tunnel_t": 3 * 2,
        "tunnel_straight": straight_val * 2,
        "tunnel_horizontal": straight_val * 2,
        "tunnel_corner_dl": corn * 2,
        "tunnel_corner_ul": corn * 2,
        "tunnel_deadend": 1 * 2,
        "tunnel_bridge": 4 * 2,
        "tunnel_double_corner": 3 * 2,
        "tunnel_split_t_up": split * 2,
        "tunnel_split_t_l": split * 2,

        "door_blue": door * 2,
        "door_green": door * 2,
        "ladder": trial.suggest_int("ladder", 1, 3) * 2,
        "act_boom": trial.suggest_int("act_boom", 1, 3) * 2,
        "act_key": trial.suggest_int("act_key", 1, 3) * 2,
        "act_map": trial.suggest_int("act_map", 1, 3) * 2,
        "brk": sabot * 2,
        "rep": sabot * 2,
    }
    # [I 2026-05-10 22:57:39,581] Trial 18 finished with value: 18.222222222222214 and parameters: {'straight_count_base': 3, 'corner_count_base': 1, 'split_count_base': 1, 'door_count_base': 2, 'sabotage_count': 1, 'tunnel_cross': 3, 'tunnel_t': 2, 'tunnel_deadend': 1, 'tunnel_bridge': 3, 'tunnel_double_corner': 2, 'ladder': 3, 'act_boom': 1, 'act_key': 1, 'act_map': 1}. Best is trial 18 with value: 18.222222222222214.
    # Попытка 18 | Штраф: 18.2 | Ничьи: 9.1%
    #   Винрейты: Агро vs Контроль: 0.52 | Контроль vs Мид: 0.55 | Агро vs Мид: 0.49
    # КРУГОВОЙ ТУРНИР
    wr_agro_vs_control, draw_ac, is_end_by_gold_ac, steps_ac = play_matchup(AGRO_PARAMS, CONTROL_PARAMS, deck_config)
    print("1")
    wr_control_vs_mid, draw_cm, is_end_by_gold_cm, steps_cm = play_matchup(CONTROL_PARAMS, MIDRANGE_PARAMS, deck_config)
    print("2")
    wr_agro_vs_mid, draw_am, is_end_by_gold_am, steps_am = play_matchup(AGRO_PARAMS, MIDRANGE_PARAMS, deck_config)
    print("3")
    # 1. ШТРАФ ЗА ДИСБАЛАНС (Каждый винрейт должен стремиться к 0.5)
    balance_penalty = (
                              abs(wr_agro_vs_control - 0.55) +
                              abs(wr_control_vs_mid - 0.55) +
                              abs(wr_agro_vs_mid - 0.45)
                      ) * 100

    # 2. ШТРАФ ЗА НИЧЬИ (Наказываем, только если ничьих в среднем больше 7%)
    avg_draws = (draw_ac + draw_cm + draw_am) / 3
    draw_penalty = max(0, avg_draws - 0.07) * 500

    total_penalty = balance_penalty + draw_penalty

    # Логируем красивые результаты
    # if total_penalty < 30:  # Если баланс почти идеальный
    print(f"Попытка {trial.number} | Штраф: {total_penalty:.1f} | Ничьи: {avg_draws * 100:.1f}%")
    print(
        f"  Винрейты: Агро vs Контроль: {wr_agro_vs_control:.2f} | Контроль vs Мид: {wr_control_vs_mid:.2f} | Агро vs Мид: {wr_agro_vs_mid:.2f} |"
        f"\n Количество побед через раскрытия всех карт золота:  Агро vs Контроль: {is_end_by_gold_ac:.2f} | Контроль vs Мид: {is_end_by_gold_cm:.2f} | Агро vs Мид: {is_end_by_gold_am:.2f} "
        f"\n Количество шагов:  Агро vs Контроль: {steps_ac:.2f} | Контроль vs Мид: {steps_cm:.2f} | Агро vs Мид: {steps_am:.2f} ")

    return total_penalty


if __name__ == "__main__":
    print("Начинаем поиск идеального баланса игры (Равновесие Нэша)...")
    study_meta = optuna.create_study(direction="minimize")
    study_meta.optimize(objective_meta_balance, n_trials=100)

    print("\n=== ИДЕАЛЬНЫЙ СОСТАВ КОЛОДЫ ===")
    for k, v in study_meta.best_params.items():
        print(f"  {k}: {v}")

    # === ДОБАВЛЕН СПОСОБ 2: Экспорт в CSV ===
    print("\nСохранение истории попыток в файл...")
    df = study_meta.trials_dataframe()
    # Сохраняем в CSV (разделитель - запятая, без столбца с индексами)
    df.to_csv("./results/game_trials_history.csv", index=False)
    print("Готово! Файл 'game_trials_history.csv' сохранен в папке с проектом.")
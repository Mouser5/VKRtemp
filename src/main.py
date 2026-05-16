import argparse
import os
import time
import logging
from typing import Dict, Type
import uuid

from game import Game
from view import ConsoleView
from cards import ActionCardTemplate, ActionType, EquipmentType, PathCardTemplate
from actions import (
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
    AgentAction,
)
from registry import REGISTRY
from random_agent import RandomAgent
from heuristic_agent import HeuristicAgent
from smart_agent import SmartAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

BOT_REGISTRY: Dict[str, Type] = {
    "random": RandomAgent,
    "heuristic": HeuristicAgent,
    "smart": SmartAgent,
}

def _format_action(action: AgentAction, game: Game) -> str:
    tpl_id = getattr(action, "template_id", None)
    tpl = REGISTRY.get(tpl_id) if tpl_id else None
    tpl_name = tpl.name if tpl else tpl_id

    if isinstance(action, ActionBuild):
        rot = " (повёрнута)" if action.is_rotated_180 else ""
        return f"ПОСТРОЙКА: {tpl_name} на ({action.x}, {action.y}){rot}"
    elif isinstance(action, ActionPlayBoardUtility):
        return f"ДЕЙСТВИЕ: {tpl_name} на ({action.x}, {action.y})"
    elif isinstance(action, ActionPlayPlayerUtility):
        target = action.target_player_id
        return f"ДЕЙСТВИЕ: {tpl_name} на игрока {target}"
    elif isinstance(action, ActionDiscard):
        if action.repair_equipment:
            return f"СБРОС + ПОЧИНКА: {action.repair_equipment.value}"
        return f"СБРОС: {len(action.templates)} карт"
    return action.type


def action_to_dsl(action: AgentAction, player_id: int) -> str:
    lines = [f"P{player_id}"]

    if isinstance(action, ActionBuild):
        lines.append("1")
        lines.append(str(action.template_id))
        lines.append(f"{action.x};{action.y}")
        lines.append("1" if action.is_rotated_180 else "0")
    elif isinstance(action, ActionPlayBoardUtility):
        lines.append("1")
        lines.append(str(action.template_id))
        lines.append(f"{action.x};{action.y}")
        lines.append("0")
    elif isinstance(action, ActionPlayPlayerUtility):
        lines.append("2")
        lines.append(str(action.template_id))
        lines.append(str(action.target_player_id))
        lines.append("0")
    elif isinstance(action, ActionDiscard):
        lines.append("3")
        if action.templates:
            lines.append(";".join(str(t) for t in action.templates))
        else:
            lines.append("")
        lines.append("0")
    else:
        lines.append("0")
        lines.append("")
        lines.append("")
        lines.append("0")

    return "\n".join(lines)


def save_game_log_to_file(
    dsl_log: str, winner: int, scores: Dict[int, int], turns: int
):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    game_id = str(uuid.uuid4())[:8]
    filename = f"game_{game_id}.txt"
    filepath = os.path.join(log_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(dsl_log)
        f.write("\n\n# Game Over\n")
        f.write(f"# Winner: P{winner}\n")
        f.write(f"# Scores: P0={scores[0]}, P1={scores[1]}\n")
        f.write(f"# Turns: {turns}\n")

    return filepath


def run_bot_match(bot1_name: str, bot2_name: str, verbose: bool = True) -> Dict:
    game = Game()
    view = ConsoleView() if verbose else None

    bot1_cls = BOT_REGISTRY.get(bot1_name.lower())
    bot2_cls = BOT_REGISTRY.get(bot2_name.lower())

    if not bot1_cls or not bot2_cls:
        raise ValueError(f"Неизвестный бот. Доступные: {list(BOT_REGISTRY.keys())}")

    agents = {0: bot1_cls(0), 1: bot2_cls(1)}

    if verbose and view:
        first = game.state.first_player_in_round
        first_name = bot1_name if first == 0 else bot2_name
        print(f"=== МАТЧ: {bot1_name} vs {bot2_name} ===")
        print(f"Первым ходит: {first_name} (игрок {first})")
        print("\n--- РАУНД 1 ---")
        view.print_board(game.state)

    turn_count = 0
    errors = []
    dsl_lines: list = []

    while not game.is_game_over():
        while not game.is_round_over():
            curr_p = game.state.current_player_id
            agent = agents[curr_p]

            try:
                action = agent.choose_action(game)
                if not action:
                    dsl_lines.append(f"P{curr_p}\n0\n\n\n0")
                    if verbose and view:
                        print(f"\nИгрок {curr_p} не имеет легальных ходов. Пропуск.")
                    game.state.current_player_id = 1 - curr_p
                    continue

                success, msg, rev_gold, _ = game.step(action)
                turn_count += 1

                dsl_lines.append(action_to_dsl(action, curr_p))

                if not success:
                    error_msg = f"Ошибка хода робота: Игрок {curr_p}, действие {action.type}, причина: {msg}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    print(f"[ОШИБКА] {error_msg}")
                    continue

                if verbose and view:
                    bot_name = bot1_name if curr_p == 0 else bot2_name
                    print(
                        f"Ход {turn_count} (Раунд {game.state.round_number}): Игрок {curr_p} ({bot_name}) -> {msg}"
                    )
                    if rev_gold:
                        print(f"  ✨ ЗОЛОТО: {rev_gold} слитков!")
                    view.print_board(game.state)
                    time.sleep(0.02)

            except Exception as e:
                error_msg = f"Ошибка хода робота: Игрок {curr_p}, исключение: {e}"
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)
                game.state.current_player_id = 1 - game.state.current_player_id

        round_ended, round_scores = game.check_round_end()
        if round_ended and round_scores:
            if verbose and view:
                print(f"\n--- РАУНД {game.state.round_number - 1} ОКОНЧЕН ---")
                print(
                    f"Очки раунда: {bot1_name}={round_scores[0]}, {bot2_name}={round_scores[1]}"
                )
                print(
                    f"Общий счёт: {bot1_name}={game.state.total_scores[0]}, {bot2_name}={game.state.total_scores[1]}"
                )
                if game.state.round_number < 3:
                    first = game.state.first_player_in_round
                    first_name = bot1_name if first == 0 else bot2_name
                    print(f"\n--- РАУНД {game.state.round_number} ---")
                    print(f"Первым ходит: {first_name} (игрок {first})")
                    view.print_board(game.state)

    total_scores = game.state.total_scores
    winner = None
    if total_scores[0] > total_scores[1]:
        winner = bot1_name
    elif total_scores[1] > total_scores[0]:
        winner = bot2_name

    result = {
        "winner": winner,
        "total_scores": total_scores,
        "turns": turn_count,
        "errors": errors,
    }

    if verbose and view:
        print("\n=== ИГРА ОКОНЧЕНА ===")
        print("Итого после 2 раундов:")
        print(f"  {bot1_name}: {total_scores[0]} очков")
        print(f"  {bot2_name}: {total_scores[1]} очков")
        if winner:
            print(f"Победитель: {winner}")
        else:
            print("Ничья!")

    dsl_log = "\n".join(dsl_lines)
    winner_idx = (
        0
        if total_scores[0] > total_scores[1]
        else (1 if total_scores[1] > total_scores[0] else -1)
    )
    log_path = save_game_log_to_file(dsl_log, winner_idx, total_scores, turn_count)
    print(f"\n📝 Лог игры сохранён в: {log_path}")

    return result


def run_benchmark(bot1_name: str, bot2_name: str, num_games: int) -> Dict:
    print(f"\n=== БЕНЧМАРК: {bot1_name} vs {bot2_name} ({num_games} игр) ===")

    bot1_cls = BOT_REGISTRY.get(bot1_name.lower())
    bot2_cls = BOT_REGISTRY.get(bot2_name.lower())

    if not bot1_cls or not bot2_cls:
        raise ValueError(f"Неизвестный бот. Доступные: {list(BOT_REGISTRY.keys())}")

    start_time = time.perf_counter()
    total_turns = 0
    empty_deck=0
    wins = {0: 0, 1: 0, "draw": 0}
    total_errors = 0

    for game_idx in range(num_games):
        game = Game()
        agents = {0: bot1_cls(0), 1: bot2_cls(1)}

        try:
            while not game.is_game_over():
                while not game.is_round_over():
                    curr_p = game.state.current_player_id
                    try:
                        action = agents[curr_p].choose_action(game)
                        if not action:
                            game.state.current_player_id = 1 - curr_p
                            continue

                        success, msg, _, _ = game.step(action)
                        # print(msg)
                        if not success:
                            total_errors += 1
                            logger.warning(f"Game {game_idx}: Ход отклонён: {msg}")
                        total_turns += 1
                    except Exception as e:
                        total_errors += 1
                        logger.error(f"Game {game_idx}: Ошибка хода робота: {e}")
                        game.state.current_player_id = 1 - game.state.current_player_id

                game.check_round_end()

            total_scores = game.state.total_scores
            if not game.state.deck:
                empty_deck+=1
            if total_scores[0] > total_scores[1]:
                wins[0] += 1
            elif total_scores[1] > total_scores[0]:
                wins[1] += 1
            else:
                wins["draw"] += 1

        except Exception as e:
            logger.critical(f"Критическая ошибка в игре {game_idx}: {e}")
            total_errors += 1

        if (game_idx + 1) % 100 == 0:
            print(f"Прогресс: {game_idx + 1}/{num_games}")

    elapsed = time.perf_counter() - start_time
    tps = total_turns / elapsed if elapsed > 0 else 0
    gps = num_games / elapsed if elapsed > 0 else 0

    print("-" * 40)
    print(f"Победы {bot1_name} (игрок 0): {wins[0]} ({100 * wins[0] / num_games:.1f}%)")
    print(f"Победы {bot2_name} (игрок 1): {wins[1]} ({100 * wins[1] / num_games:.1f}%)")
    print(f"Ничьи: {wins['draw']}")
    print("-" * 40)
    print(f"Пустая колода: {empty_deck}")
    print(f"Всего ходов: {total_turns}")
    print(f"Ошибок: {total_errors}")
    print(f"Время: {elapsed:.2f} сек")
    print(f"Ходов/сек: {tps:.0f}")
    print(f"Игр/сек: {gps:.1f}")

    return {
        "wins": wins,
        "total_turns": total_turns,
        "total_errors": total_errors,
        "time": elapsed,
        "tps": tps,
        "gps": gps,
    }


def interactive_loop(game: Game, view: ConsoleView):
    while True:
        if game.is_game_over():
            view.print_message("\n" + "=" * 50)
            view.print_message("ИГРА ОКОНЧЕНА!")
            view.print_board(game.state)
            scores = game.calculate_scores()
            print(f"ИТОГОВЫЙ СЧЕТ: Игрок 0: {scores[0]}, Игрок 1: {scores[1]}")
            break

        view.print_message("\n" + "=" * 50)
        view.print_board(game.state)
        view.print_hand(game.state)

        print("\nДействия:")
        print("1. Сыграть карту")
        print("2. Сбросить карты (1-2 шт)")
        print("3. Экстренная починка (сбросить 2 карты)")
        print("4. Выход")

        choice = input("\nВыбор: ").strip()
        if choice == "4":
            break

        if choice == "1":
            try:
                c_idx = int(input("Введите номер карты из руки: "))
                p_id = game.state.current_player_id
                t_id = game.state.players[p_id].hand[c_idx]
                tpl_id = game.state.players[p_id].card_id_to_template[t_id]
                tpl = REGISTRY.get(tpl_id)

                action = None
                if isinstance(tpl, PathCardTemplate) or (
                    isinstance(tpl, ActionCardTemplate)
                    and tpl.action_type
                    in [ActionType.KEY, ActionType.ROCKFALL, ActionType.MAP]
                ):
                    coords = input("Введите координаты поля (x y): ").split()
                    x, y = int(coords[0]), int(coords[1])
                    rot = False
                    if isinstance(tpl, PathCardTemplate):
                        rot = input("Повернуть карту? (y/n): ").strip().lower() == "y"

                    if isinstance(tpl, PathCardTemplate):
                        action = ActionBuild(
                            template_id=t_id, x=x, y=y, is_rotated_180=rot
                        )
                    else:
                        action = ActionPlayBoardUtility(template_id=t_id, x=x, y=y)

                elif isinstance(tpl, ActionCardTemplate) and tpl.action_type in [
                    ActionType.SABOTAGE,
                    ActionType.REPAIR,
                ]:
                    t_target = int(input("Укажите цель (номер игрока 0 или 1): "))
                    action = ActionPlayPlayerUtility(
                        template_id=t_id, target_player_id=t_target
                    )
                else:
                    continue

                success, msg, rev_gold, _ = game.step(action)
                if success:
                    view.print_message(msg)
                    if rev_gold:
                        view.print_message(f"✨ ЗОЛОТО НАЙДЕНО: {rev_gold} слитков! ✨")
                else:
                    view.print_message(msg, is_error=True)

            except Exception as e:
                view.print_message(f"Ошибка: {e}", is_error=True)

        elif choice == "2":
            try:
                indices = [int(i) for i in input("Номера карт через пробел: ").split()]
                p_id = game.state.current_player_id
                templates = [game.state.players[p_id].hand[i] for i in indices]

                action = ActionDiscard(templates=templates)
                success, msg, _, _ = game.step(action)
                if not success:
                    view.print_message(msg, is_error=True)
            except Exception as e:
                view.print_message(f"Ошибка ввода: {e}", is_error=True)

        elif choice == "3":
            try:
                indices = [int(i) for i in input("Укажите 2 номера карт: ").split()]
                print("Какой предмет чиним? 1 - Лампа, 2 - Вагонетка, 3 - Кирка")
                eq_map = {
                    "1": EquipmentType.LAMP,
                    "2": EquipmentType.CART,
                    "3": EquipmentType.PICKAXE,
                }
                eq_choice = input("Выбор: ").strip()

                if eq_choice in eq_map:
                    p_id = game.state.current_player_id
                    templates = [game.state.players[p_id].hand[i] for i in indices]

                    action = ActionDiscard(
                        templates=templates, repair_equipment=eq_map[eq_choice]
                    )
                    success, msg, _, _ = game.step(action)
                    if success:
                        view.print_message(msg)
                    else:
                        view.print_message(msg, is_error=True)
            except Exception as e:
                view.print_message(f"Ошибка ввода: {e}", is_error=True)


def main():
    parser = argparse.ArgumentParser(
        description="Гномы-вредители: Дуэль - карточная игра",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main.py                                    # Интерактивная игра
  python main.py --bot-vs-bot --bot1 random --bot2 heuristic
  python main.py --benchmark 100 --bot1 heuristic --bot2 random
        """,
    )

    parser.add_argument(
        "--bot-vs-bot",
        action="store_true",
        help="Запустить 1 игру двух ботов с подробным логом",
    )
    parser.add_argument(
        "--benchmark",
        type=int,
        metavar="N",
        help="Запустить N игр двух ботов без подробного лога",
    )
    parser.add_argument(
        "--bot1",
        type=str,
        default="random",
        help=f"Имя первого бота. Доступные: {list(BOT_REGISTRY.keys())}",
    )
    parser.add_argument(
        "--bot2",
        type=str,
        default="heuristic",
        help=f"Имя второго бота. Доступные: {list(BOT_REGISTRY.keys())}",
    )

    args = parser.parse_args()

    if args.bot_vs_bot:
        run_bot_match(args.bot1, args.bot2, verbose=True)
    elif args.benchmark:
        run_benchmark(args.bot1, args.bot2, args.benchmark)
    else:
        print("=== ИНТЕРАКТИВНЫЙ РЕЖИМ ===")
        print("Доступные боты для --bot-vs-bot и --benchmark:")
        for name in BOT_REGISTRY:
            print(f"  - {name}")
        print()
        g = Game()
        v = ConsoleView()
        interactive_loop(g, v)


if __name__ == "__main__":
    main()
    # run_bot_match("heuristic", "smart", True)
    #run_benchmark("heuristic", "smart",300)
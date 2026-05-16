import sys
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Game
from actions import (
    AgentAction,
    ActionBuild,
    ActionPlayBoardUtility,
    ActionPlayPlayerUtility,
    ActionDiscard,
)
from registry import REGISTRY
from random_agent import RandomAgent
from heuristic_agent import HeuristicAgent
from smart_agent import SmartAgent
from view import ConsoleView


BUILTIN_AGENTS = {
    "random": RandomAgent,
    "heuristic": HeuristicAgent,
    "smart": SmartAgent,
}


@dataclass
class GameLog:
    turn_number: int
    round_number: int
    player_id: int
    action_type: str
    action_description: str
    message: str | None = None
    action_dsl: str | None = None
    gold_found: Optional[int] = None


@dataclass
class SingleGameResult:
    winner: Optional[int]
    winner_name: str
    total_scores: Dict[int, int]
    turns: int
    errors: List[str]
    logs: List[GameLog] = field(default_factory=list)
    round_scores: List[Dict[int, int]] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    wins: Dict[str, int]
    total_games: int
    total_turns: int
    total_errors: int
    elapsed_time: float
    games_per_second: float
    turns_per_second: float


@dataclass
class TournamentResult:
    tournament_id: int
    total_games: int
    total_turns: int
    results: Dict[str, Dict[str, int]]
    elapsed_time: float


def _format_action(action: AgentAction, game: Game) -> str:
    tpl_id = getattr(action, "template_id", None)
    _tpl_id = game.get_template_by_card_id(tpl_id)

    tpl = REGISTRY.get(_tpl_id) if _tpl_id else None
    tpl_name = tpl.name if tpl else _tpl_id

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
    return str(action.type)


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


def save_game_log_to_db(
    db_session,
    game_id: str,
    dsl_log: str,
    scores_p0: int,
    scores_p1: int,
    winner: Optional[int],
    turns: int,
    bot1_code: Optional[str] = None,
    bot2_code: Optional[str] = None,
):
    from web.models import GameLog

    game_log = GameLog(
        game_id=game_id,
        bot1_code=bot1_code,
        bot2_code=bot2_code,
        dsl_log=dsl_log,
        scores_p0=scores_p0,
        scores_p1=scores_p1,
        winner=winner,
        turns=turns,
    )
    db_session.add(game_log)
    db_session.commit()


def run_single_game(
    agent1_class: type,
    agent2_class: type,
    agent1_name: str = "Агент 1",
    agent2_name: str = "Агент 2",
    verbose: bool = True,
    db_session=None,
    game_id: str = None,
    save_to_db: bool = False,
) -> SingleGameResult:
    game = Game()
    agents = {
        0: agent1_class(0),
        1: agent2_class(1),
    }

    logs: List[GameLog] = []
    errors: List[str] = []
    round_scores: List[Dict[int, int]] = []
    turn_count = 0
    dsl_lines: List[str] = []

    while not game.is_game_over():
        while not game.is_round_over():
            curr_p = game.state.current_player_id
            agent = agents[curr_p]

            try:
                action = agent.choose_action(game)
                if not action:
                    logs.append(
                        GameLog(
                            turn_number=turn_count,
                            round_number=game.state.round_number,
                            player_id=curr_p,
                            action_type="skip",
                            action_description="Нет легальных ходов",
                            message="Пропуск хода",
                        )
                    )
                    dsl_lines.append(f"P{curr_p}\n0\n\n\n0")
                    game.state.current_player_id = 1 - curr_p
                    continue

                success, msg, rev_gold = game.step(action)
                turn_count += 1

                dsl_lines.append(action_to_dsl(action, curr_p))

                agent_name = agent1_name if curr_p == 0 else agent2_name
                action_desc = _format_action(action, game)

                logs.append(
                    GameLog(
                        turn_number=turn_count,
                        round_number=game.state.round_number,
                        player_id=curr_p,
                        action_type=action.type,
                        action_description=action_desc,
                        message=msg,
                        gold_found=rev_gold,
                    )
                )

                if not success:
                    error_msg = f"Ход отклонён: {msg}"
                    errors.append(error_msg)
                    raise RuntimeError(error_msg)

            except Exception as e:
                error_msg = (
                    f"Ошибка агента {curr_p}: {str(e)}\n{traceback.format_exc()}"
                )
                errors.append(error_msg)
                return SingleGameResult(
                    winner=None,
                    winner_name="ОШИБКА",
                    total_scores=game.state.total_scores.copy(),
                    turns=turn_count,
                    errors=errors,
                    logs=logs,
                    round_scores=round_scores,
                )

        round_ended, round_score = game.check_round_end()
        if round_ended and round_score:
            round_scores.append(round_score.copy())

    total_scores = game.state.total_scores
    winner = None
    winner_name = "Ничья"

    if total_scores[0] > total_scores[1]:
        winner = 0
        winner_name = agent1_name
    elif total_scores[1] > total_scores[0]:
        winner = 1
        winner_name = agent2_name

    if save_to_db and db_session and game_id:
        dsl_log = "\n".join(dsl_lines)
        save_game_log_to_db(
            db_session=db_session,
            game_id=game_id,
            dsl_log=dsl_log,
            scores_p0=total_scores[0],
            scores_p1=total_scores[1],
            winner=winner,
            turns=turn_count,
        )

    return SingleGameResult(
        winner=winner,
        winner_name=winner_name,
        total_scores=total_scores,
        turns=turn_count,
        errors=errors,
        logs=logs,
        round_scores=round_scores,
    )


def run_benchmark(
    agent1_class: type,
    agent2_class: type,
    num_games: int,
    agent1_name: str = "Агент 1",
    agent2_name: str = "Агент 2",
) -> BenchmarkResult:
    start_time = time.perf_counter()
    total_turns = 0
    total_errors = 0
    wins = {agent1_name: 0, agent2_name: 0, "draw": 0}

    for game_idx in range(num_games):
        game = Game()
        agents = {
            0: agent1_class(0),
            1: agent2_class(1),
        }

        try:
            while not game.is_game_over():
                while not game.is_round_over():
                    curr_p = game.state.current_player_id
                    try:
                        action = agents[curr_p].choose_action(game)
                        if not action:
                            game.state.current_player_id = 1 - curr_p
                            continue

                        success, msg, _ = game.step(action)
                        if not success:
                            total_errors += 1
                        total_turns += 1
                    except Exception:
                        total_errors += 1
                        game.state.current_player_id = 1 - game.state.current_player_id

                game.check_round_end()

            total_scores = game.state.total_scores
            if total_scores[0] > total_scores[1]:
                wins[agent1_name] += 1
            elif total_scores[1] > total_scores[0]:
                wins[agent2_name] += 1
            else:
                wins["draw"] += 1

        except Exception:
            total_errors += 1

    elapsed = time.perf_counter() - start_time
    tps = total_turns / elapsed if elapsed > 0 else 0
    gps = num_games / elapsed if elapsed > 0 else 0

    return BenchmarkResult(
        wins=wins,
        total_games=num_games,
        total_turns=total_turns,
        total_errors=total_errors,
        elapsed_time=elapsed,
        games_per_second=gps,
        turns_per_second=tps,
    )


def get_board_ascii(game: Game) -> str:
    view = ConsoleView()
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        view.print_board(game.state)

    return f.getvalue()


def create_game_for_tournament(
    agent1_class: type,
    agent2_class: type,
    hand1: List[int],
    hand2: List[int],
    hand1_templates: List[str],
    hand2_templates: List[str],
) -> Game:
    print(f"   [DEBUG] Creating game with hands - P0: {hand1}, P1: {hand2}")
    game = Game()
    print(
        f"   [DEBUG] Game created - board size: {len(game.state.board)}, deck size: {len(game.state.deck)}"
    )

    original_deck = game.state.deck.copy()
    original_deck_template_ids = game.state.deck_template_ids.copy()

    game.state.board.clear()
    print(f"   [DEBUG] Board cleared - board size: {len(game.state.board)}")

    game.state.gold_deck = [
        "gold_1_ud",
        "gold_1_lr",
        "gold_2_corner",
        "gold_2_t",
        "gold_3_cross",
        "gold_3_t",
    ]

    game._setup_board()
    print(
        f"   [DEBUG] Board setup done - gold positions: {[k for k, v in game.state.board.items() if 'gold' in v.template_id]}"
    )

    game.state.deck = original_deck
    game.state.deck_template_ids = original_deck_template_ids

    game.state.players[0].hand = hand1.copy()
    game.state.players[1].hand = hand2.copy()
    game.state.players[0].card_id_to_template = dict(zip(hand1, hand1_templates))
    game.state.players[1].card_id_to_template = dict(zip(hand2, hand2_templates))

    print(
        f"   [DEBUG] Hands restored - P0: {game.state.players[0].hand}, P1: {game.state.players[1].hand}"
    )

    return game


from concurrent.futures import ThreadPoolExecutor, as_completed
from web.database import SessionLocal
from web.redis_game_bridge import RedisGameBridge


def run_tournament(
    bots: List[Tuple[str, type, str]],
    db_session,
    user_id: int,
    tournament_name: str,
) -> TournamentResult:
    from web.models import Tournament, TournamentGame, TournamentResult as TRModel, TournamentStatus, User
    from web.logger import log_tournament_end

    start_time = time.perf_counter()
    tournament = Tournament(user_id=user_id, name=tournament_name, status=TournamentStatus.running)
    db_session.add(tournament)
    db_session.commit()
    tournament_id = tournament.id

    results = {b_name: {"wins": 0, "losses": 0, "draws": 0, "total_score": 0, "games": 0} for _, _, b_name in bots}

    match_tasks = []
    game_order = 1
    for i, (bot1_code, _, bot1_name) in enumerate(bots):
        for j, (bot2_code, _, bot2_name) in enumerate(bots[i + 1:], start=i + 1):
            match_tasks.append({
                "order": game_order,
                "p0_name": bot1_name, "p0_code": bot1_code,
                "p1_name": bot2_name, "p1_code": bot2_code,
            })
            game_order += 1

    total_games = 0
    total_turns = 0

    print(f"\n[TOURNAMENT] Starting {len(match_tasks)} matches with 10 parallel workers")
    bridge = RedisGameBridge()

    def worker_task(match_info):
        """Задача для ThreadPoolExecutor. Внутри создаем свою сессию БД."""
        db = SessionLocal()
        try:
            # Запускаем игру в двух изолированных контейнерах через Redis мост
            res = bridge.run_game_two_containers(
                bot0_name=match_info["p0_name"],
                bot1_name=match_info["p1_name"],
                bot0_code=match_info["p0_code"],
                bot1_code=match_info["p1_code"]
            )

            # Логируем результат игры в БД
            scores = res.get("scores", {0: 0, 1: 0})
            tg = TournamentGame(
                tournament_id=tournament_id,
                bot1_name=match_info["p0_name"],
                bot2_name=match_info["p1_name"],
                game_order=match_info["order"],
                bot1_score=scores.get(0, 0),
                bot2_score=scores.get(1, 0),
                winner=res.get("winner"),
                turns=res.get("turns", 0),
            )
            db.add(tg)
            db.commit()

            res["p0_name"] = match_info["p0_name"]
            res["p1_name"] = match_info["p1_name"]
            return res
        finally:
            db.close()

    # Запускаем пул потоков (МАКСИМУМ 10 параллельно)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_task, match) for match in match_tasks]

        for future in as_completed(futures):
            res = future.result()
            total_games += 1
            total_turns += res.get("turns", 0)

            b1 = res["p0_name"]
            b2 = res["p1_name"]
            winner = res.get("winner")
            scores = res.get("scores", {0: 0, 1: 0})

            # Обновляем локальный словарь результатов
            if winner == 0:
                results[b1]["wins"] += 1
                results[b2]["losses"] += 1
            elif winner == 1:
                results[b1]["losses"] += 1
                results[b2]["wins"] += 1
            else:
                results[b1]["draws"] += 1
                results[b2]["draws"] += 1

            results[b1]["total_score"] += scores.get(0, 0)
            results[b2]["total_score"] += scores.get(1, 0)
            results[b1]["games"] += 1
            results[b2]["games"] += 1

    # Сохраняем финальные результаты турнира в БД
    for bot_name, stats in results.items():
        tr = TRModel(
            tournament_id=tournament_id,
            bot_name=bot_name,
            wins=stats["wins"],
            losses=stats["losses"],
            draws=stats["draws"],
            total_score=stats["total_score"],
            games_played=stats["games"],
        )
        db_session.add(tr)

    tournament.status = TournamentStatus.completed
    db_session.commit()

    elapsed = time.perf_counter() - start_time
    log_tournament_end(tournament_id, tournament_name, total_games, total_turns, results, elapsed)

    return TournamentResult(tournament_id, total_games, total_turns, results, elapsed)

def run_single_game_internal(
    game: Game,
    agents: Dict[int, object],
    agent1_name: str,
    agent2_name: str,
) -> Dict:
    turn_count = 0
    errors = []

    print(f"   [GAME DEBUG] Starting game: {agent1_name} vs {agent2_name}")
    print(f"   [GAME DEBUG] Initial board: {len(game.state.board)} cards")
    print(
        f"   [GAME DEBUG] Initial hands - P0: {game.state.players[0].hand}, P1: {game.state.players[1].hand}"
    )
    print(f"   [GAME DEBUG] Initial deck size: {len(game.state.deck)}")
    print(f"   [GAME DEBUG] Initial gold deck size: {len(game.state.gold_deck)}")
    print(
        f"   [GAME DEBUG] is_game_over: {game.is_game_over()}, is_round_over: {game.is_round_over()}"
    )

    while not game.is_game_over():
        while not game.is_round_over():
            curr_p = game.state.current_player_id
            agent = agents[curr_p]

            try:
                action = agent.choose_action(game)
                if not action:
                    print(f"   [GAME DEBUG] No legal actions for player {curr_p}")
                    game.state.current_player_id = 1 - curr_p
                    continue

                success, msg, rev_gold = game.step(action)
                turn_count += 1

                if turn_count <= 5:
                    print(
                        f"   [GAME DEBUG] Turn {turn_count}: P{curr_p} action={action}, success={success}, msg={msg}, gold={rev_gold}"
                    )

                if not success:
                    errors.append(f"Ход отклонён: {msg}")
                    raise RuntimeError(msg)

            except Exception as e:
                errors.append(f"Ошибка агента {curr_p}: {str(e)}")
                print(f"   [GAME DEBUG] ERROR: {e}")
                return {
                    "winner": None,
                    "scores": {0: 0, 1: 0},
                    "turns": turn_count,
                    "errors": errors,
                }

        print(
            f"   [GAME DEBUG] Round ended, checking... is_round_over: {game.is_round_over()}"
        )
        game.check_round_end()
        print(
            f"   [GAME DEBUG] After check_round_end - is_game_over: {game.is_game_over()}, round_number: {game.state.round_number}"
        )

    total_scores = game.state.total_scores
    print(
        f"   [GAME DEBUG] Game over! Scores: P0={total_scores[0]}, P1={total_scores[1]}"
    )

    winner = None
    if total_scores[0] > total_scores[1]:
        winner = 0
    elif total_scores[1] > total_scores[0]:
        winner = 1

    return {
        "winner": winner,
        "scores": total_scores,
        "turns": turn_count,
        "errors": errors,
    }

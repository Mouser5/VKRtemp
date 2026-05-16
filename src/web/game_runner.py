import sys
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Game
from mc_config import GameConfig
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


@dataclass
class HyperparamResult:
    wins: Dict[str, int]
    total_games: int
    total_turns: int
    total_errors: int
    elapsed_time: float
    games_per_second: float
    turns_per_second: float
    winrate_history: Dict[str, List[float]]


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

                success, msg, rev_gold, _ = game.step(action)
                turn_count += 1

                dsl_lines.append(action_to_dsl(action, curr_p))

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

                        success, msg, _, _ = game.step(action)
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


def run_hyperparam_benchmark(
    agent1_class: type,
    agent2_class: type,
    num_games: int,
    config: GameConfig = None,
    agent1_name: str = "Агент 1",
    agent2_name: str = "Агент 2",
) -> HyperparamResult:
    if config is None:
        config = GameConfig()

    start_time = time.perf_counter()
    total_turns = 0
    total_errors = 0
    wins = {agent1_name: 0, agent2_name: 0, "draw": 0}

    agent1_wins_acc = 0
    winrate_history: Dict[str, List[float]] = {agent1_name: [], agent2_name: []}

    for game_idx in range(num_games):
        game = Game(config=config)
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

                        success, msg, _, _ = game.step(action)
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

        agent1_wins_acc = wins[agent1_name]
        games_played = game_idx + 1
        winrate_history[agent1_name].append(agent1_wins_acc / games_played * 100)
        winrate_history[agent2_name].append(
            (games_played - agent1_wins_acc - wins["draw"]) / games_played * 100
        )

    elapsed = time.perf_counter() - start_time
    tps = total_turns / elapsed if elapsed > 0 else 0
    gps = num_games / elapsed if elapsed > 0 else 0

    return HyperparamResult(
        wins=wins,
        total_games=num_games,
        total_turns=total_turns,
        total_errors=total_errors,
        elapsed_time=elapsed,
        games_per_second=gps,
        turns_per_second=tps,
        winrate_history=winrate_history,
    )


def get_board_ascii(game: Game) -> str:
    view = ConsoleView()
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        view.print_board(game.state)

    return f.getvalue()


def run_tournament(
    bots: List[Tuple[str, type, str]],
    db_session,
    user_id: int,
    tournament_name: str,
) -> TournamentResult:
    from web.models import (
        Tournament,
        TournamentGame,
        TournamentResult as TRModel,
        TournamentStatus,
    )
    from web.logger import log_tournament_end, log_tournament_game

    start_time = time.perf_counter()
    tournament = Tournament(
        user_id=user_id, name=tournament_name, status=TournamentStatus.running
    )
    db_session.add(tournament)
    db_session.commit()
    tournament_id = tournament.id

    results = {
        b_name: {"wins": 0, "losses": 0, "draws": 0, "total_score": 0, "games": 0}
        for _, _, b_name in bots
    }

    total_games = 0
    total_turns = 0

    print(f"\n[TOURNAMENT] Starting tournament with {len(bots)} bots")
    from web.redis_game_bridge import RedisGameBridge

    bridge = RedisGameBridge()

    for i in range(len(bots)):
        for j in range(len(bots)):
            if i == j:
                continue
            bot1_code, bot1_class, bot1_name = bots[i]
            bot2_code, bot2_class, bot2_name = bots[j]

            print(f"\n[TOURNAMENT] Match: {bot1_name} vs {bot2_name}")

            container_code = bot1_code
            container_name, opponent_name = bot1_name, bot2_name
            container_player_id = 0
            opponent_agent = bot2_class(1)

            game = Game()

            result = bridge.run_with_container(
                container_player_id=container_player_id,
                bot_code=container_code,
                opponent_agent=opponent_agent,
                opponent_name=opponent_name,
                bot_name=container_name,
                game=game,
            )

            if result.get("error"):
                print(f"[TOURNAMENT] Game error: {result['error']}")
                result["winner"] = None
                result["scores"] = {0: 0, 1: 0}
                result["turns"] = 0

            print(
                f"[TOURNAMENT] Result: winner={result['winner']}, scores={result['scores']}, turns={result['turns']}"
            )
            total_turns += result["turns"]

            if container_name == bot1_name:
                bot1_score = result["scores"][0]
                bot2_score = result["scores"][1]
            else:
                bot1_score = result["scores"][1]
                bot2_score = result["scores"][0]

            tg = TournamentGame(
                tournament_id=tournament_id,
                bot1_id=None,
                bot2_id=None,
                bot1_name=bot1_name,
                bot2_name=bot2_name,
                game_order=total_games + 1,
                bot1_score=bot1_score,
                bot2_score=bot2_score,
                winner=result["winner"],
                turns=result["turns"],
            )
            db_session.add(tg)
            db_session.commit()

            log_tournament_game(
                tournament_id=tournament_id,
                game_num=total_games + 1,
                bot1_name=bot1_name,
                bot2_name=bot2_name,
                bot1_score=bot1_score,
                bot2_score=bot2_score,
                winner=result["winner"],
                turns=result["turns"],
            )

            if result["winner"] == 0:
                winning_bot = container_name
                losing_bot = opponent_name
            elif result["winner"] == 1:
                winning_bot = opponent_name
                losing_bot = container_name
            else:
                winning_bot = losing_bot = None

            if winning_bot:
                results[winning_bot]["wins"] += 1
                results[losing_bot]["losses"] += 1
            else:
                results[bot1_name]["draws"] += 1
                results[bot2_name]["draws"] += 1

            results[container_name]["total_score"] += result["scores"][0]
            results[opponent_name]["total_score"] += result["scores"][1]
            results[bot1_name]["games"] += 1
            results[bot2_name]["games"] += 1
            total_games += 1

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
    log_tournament_end(
        tournament_id, tournament_name, total_games, total_turns, results, elapsed
    )

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

                success, msg, rev_gold, _ = game.step(action)
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
